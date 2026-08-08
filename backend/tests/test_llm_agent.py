"""Tests for LLM-driven planning and narration, and for how they degrade.

No network. A StaticProvider returns canned completions, which is the only honest way to
test that a hostile or careless model output is handled — you cannot ask a real model to
misbehave on demand.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from algorithms.agent.llm import (
    LlmUnavailableError,
    NullProvider,
    StaticProvider,
    build_provider,
    extract_json,
)
from algorithms.agent.llm_planner import LlmNarrator, LlmPlanner
from algorithms.agent.planner import parse_intent
from app.core.config import Settings
from app.core.db import get_session
from app.main import create_app
from app.models import Base
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

GOOD_PLAN = json.dumps(
    {
        "steps": [
            {"step_id": "s1", "tool": "profile_dataset", "depends_on": [], "parameters": {}},
            {
                "step_id": "s2",
                "tool": "detect_dynamic_segments",
                "depends_on": ["s1"],
                "parameters": {"window_size": 80},
            },
            {"step_id": "s3", "tool": "fit_arx", "depends_on": ["s2"], "parameters": {}},
        ],
        "assumptions": ["按工程师要求提取动态段后直接建模。"],
    },
    ensure_ascii=False,
)


def plan_with(response: str):  # type: ignore[no-untyped-def]
    planner = LlmPlanner(StaticProvider(responses=[response]))
    return planner.plan("提取动态数据并建模", parse_intent("提取动态数据并建模"))


class TestJsonExtraction:
    def test_reads_plain_json(self) -> None:
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_reads_a_fenced_block(self) -> None:
        assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_reads_json_wrapped_in_prose(self) -> None:
        assert extract_json('好的，计划如下：\n{"a": 1}\n希望有帮助') == {"a": 1}

    def test_raises_when_nothing_parses(self) -> None:
        with pytest.raises(ValueError):
            extract_json("这里完全没有 JSON")


class TestProviderConstruction:
    def test_disabled_provider_is_null(self) -> None:
        provider = build_provider(provider="none", base_url="", model="", api_key="")
        assert isinstance(provider, NullProvider)

    def test_missing_base_url_falls_back_to_null(self) -> None:
        provider = build_provider(provider="deepseek", base_url="", model="x", api_key="k")
        assert isinstance(provider, NullProvider)

    def test_configured_provider_is_built(self) -> None:
        provider = build_provider(
            provider="ollama", base_url="http://localhost:11434/v1", model="qwen2.5", api_key=""
        )
        assert not isinstance(provider, NullProvider)
        assert provider.model == "qwen2.5"

    def test_null_provider_raises_rather_than_returning_nothing(self) -> None:
        with pytest.raises(LlmUnavailableError):
            NullProvider().complete([])


class TestLlmPlanning:
    def test_a_valid_plan_is_adopted(self) -> None:
        outcome = plan_with(GOOD_PLAN)
        assert outcome.llm_authored
        assert [step.tool for step in outcome.steps] == [
            "profile_dataset",
            "detect_dynamic_segments",
            "fit_arx",
        ]
        assert outcome.steps[1].parameters["window_size"] == 80
        assert outcome.fallback_reason is None

    def test_an_invented_tool_is_refused(self) -> None:
        """The model does not get to expand its own capability surface."""

        rogue = json.dumps(
            {"steps": [{"step_id": "s1", "tool": "execute_python", "depends_on": []}]}
        )
        outcome = plan_with(rogue)
        assert not outcome.llm_authored
        assert "非白名单工具" in (outcome.fallback_reason or "")

    def test_a_plan_that_fails_compliance_is_refused(self) -> None:
        leaky = json.dumps(
            {
                "steps": [
                    {
                        "step_id": "s1",
                        "tool": "fit_arx",
                        "depends_on": [],
                        "parameters": {"partition": "test"},
                    }
                ]
            }
        )
        outcome = plan_with(leaky)
        assert not outcome.llm_authored
        assert "合规校验" in (outcome.fallback_reason or "")

    def test_the_model_cannot_unlock_an_unconfirmed_export(self) -> None:
        """requires_confirmation comes from the whitelist, never from the completion."""

        sneaky = json.dumps(
            {
                "steps": [
                    {"step_id": "s1", "tool": "profile_dataset", "depends_on": []},
                    {
                        "step_id": "s2",
                        "tool": "export_dataset",
                        "depends_on": ["s1"],
                        "requires_confirmation": False,
                    },
                ]
            }
        )
        outcome = plan_with(sneaky)
        export = next(step for step in outcome.steps if step.tool == "export_dataset")
        assert export.requires_confirmation is True

    def test_malformed_output_falls_back(self) -> None:
        outcome = plan_with("我不太确定，要不你再说一遍？")
        assert not outcome.llm_authored
        assert "无法解析" in (outcome.fallback_reason or "")

    def test_an_empty_plan_falls_back(self) -> None:
        outcome = plan_with(json.dumps({"steps": []}))
        assert not outcome.llm_authored
        assert "空计划" in (outcome.fallback_reason or "")

    def test_an_unavailable_provider_falls_back_with_a_reason(self) -> None:
        planner = LlmPlanner(NullProvider())
        outcome = planner.plan("清洗后建模", parse_intent("清洗后建模"))
        assert not outcome.llm_authored
        assert outcome.fallback_reason
        assert [step.tool for step in outcome.steps][0] == "profile_dataset"


class TestLlmNarration:
    def test_a_placeholder_only_draft_is_accepted(self) -> None:
        draft = "验证集自由仿真 FIT 为 {{run:r1.validation.free_run_fit}}，模型可用于多步预测。"
        outcome = LlmNarrator(StaticProvider(responses=[draft])).narrate(
            context="已完成辨识", available_paths=["r1.validation.free_run_fit"]
        )
        assert outcome.source == "llm"
        assert outcome.text == draft
        assert outcome.attempts == 1

    def test_a_draft_with_a_bare_number_is_retried_then_rejected(self) -> None:
        """The anti-hallucination guarantee, exercised against a model that ignores it."""

        outcome = LlmNarrator(
            StaticProvider(responses=["拟合度高达 97.86%，非常理想。"]), max_attempts=3
        ).narrate(context="已完成辨识", available_paths=["r1.validation.free_run_fit"])
        assert outcome.source == "template"
        assert outcome.text == ""
        assert outcome.attempts == 3
        assert outcome.violations
        assert "97.86" in {violation["text"] for violation in outcome.violations}

    def test_a_model_that_corrects_itself_is_accepted(self) -> None:
        outcome = LlmNarrator(
            StaticProvider(
                responses=[
                    "FIT 达到 97.86%。",
                    "FIT 达到 {{run:r1.validation.free_run_fit}}。",
                ]
            )
        ).narrate(context="已完成辨识", available_paths=["r1.validation.free_run_fit"])
        assert outcome.source == "llm"
        assert outcome.attempts == 2

    def test_an_unavailable_provider_yields_the_template(self) -> None:
        outcome = LlmNarrator(NullProvider()).narrate(context="x", available_paths=[])
        assert outcome.source == "template"
        assert outcome.fallback_reason


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'llm.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(prepare())

    async def session_override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    monkeypatch.setattr("app.api.routes.get_settings", lambda: Settings(artifact_root=tmp_path))
    app = create_app()
    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        yield client
    asyncio.run(engine.dispose())


class TestDefaultDeployment:
    def test_offline_default_still_plans_and_says_why(self, client: TestClient) -> None:
        """No provider configured is the supported default, not a broken state."""

        response = client.post("/api/v1/copilot/chat", json={"message": "清洗数据后做 ARX 辨识"})
        assert response.status_code == 200, response.text
        data = response.json()["data"]

        assert data["plan_source"] == "rule_based"
        assert data["llm_provider"] == "none"
        assert data["llm_fallback_reason"]
        assert data["compliance"]["passed"] is True
        assert any("未采用大模型计划" in note for note in data["plan"]["assumptions"])

    def test_report_reports_its_narration_source(self, client: TestClient) -> None:
        generated = client.post(
            "/api/v1/simulation/generate",
            json={"scenario": "S2", "n_steps": 2000, "seed": 6, "input_count": 2},
        )
        version_id = generated.json()["data"]["version_id"]
        client.post(
            "/api/v1/preprocessing/segment",
            json={
                "version_id": version_id,
                "input_columns": ["u1", "u2"],
                "output_column": "y",
                "window_size": 60,
                "max_segments": 5,
            },
        )
        report = client.post("/api/v1/reports/generate", json={"version_id": version_id})
        assert report.status_code == 200, report.text
        data = report.json()["data"]
        assert data["narration_source"] == "template"
        assert data["fully_resolved"] is True
