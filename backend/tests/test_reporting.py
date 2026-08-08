"""Tests for provenance-bound reporting and optimised-dataset export (phase 10)."""

from __future__ import annotations

import asyncio
import csv
import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from algorithms.report.provenance import (
    render_template,
    resolve_path,
    validate_draft,
)
from app.core.config import Settings
from app.core.db import get_session
from app.main import create_app
from app.models import Base
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

RUNS = {
    "r1": {
        "run_type": "modeling.arx",
        "validation": {"free_run_fit": 97.8612, "one_step_fit": 99.1, "stable": True},
        "training_rows": 480,
        "delays": {"u1": 3, "u2": 8},
    }
}


class TestNumeralValidation:
    def test_a_bare_number_is_rejected(self) -> None:
        violations = validate_draft("验证集自由仿真 FIT 达到 97.86%。")
        assert len(violations) == 1
        assert violations[0].text == "97.86"

    def test_a_bound_number_is_accepted(self) -> None:
        draft = "验证集自由仿真 FIT 达到 {{run:r1.validation.free_run_fit}}%。"
        assert validate_draft(draft) == []

    def test_list_and_heading_numbering_is_allowed(self) -> None:
        draft = "## 1. 概述\n\n1. 第一条\n2) 第二条\n3、第三条\n"
        assert validate_draft(draft) == []

    def test_a_number_after_a_list_marker_is_still_rejected(self) -> None:
        """Structure is exempt; data on the same line is not."""

        violations = validate_draft("1. 拟合度为 88.2 分")
        assert [violation.text for violation in violations] == ["88.2"]

    def test_reports_line_and_column(self) -> None:
        violations = validate_draft("第一行没有数字\n第二行有 42")
        assert violations[0].line == 2
        assert violations[0].column > 1

    def test_a_markdown_table_separator_is_not_data(self) -> None:
        assert validate_draft("| a | b |\n|---|---:|\n") == []

    def test_catches_every_violation_not_just_the_first(self) -> None:
        violations = validate_draft("FIT 97.8，RMSE 0.12，条件数 3400")
        assert len(violations) == 3


class TestPathResolution:
    def test_reads_a_nested_path(self) -> None:
        assert resolve_path(RUNS["r1"], "validation.free_run_fit") == pytest.approx(97.8612)

    def test_reads_a_dict_leaf(self) -> None:
        assert resolve_path(RUNS["r1"], "delays.u1") == 3

    def test_reads_a_list_index(self) -> None:
        assert resolve_path({"values": [10, 20, 30]}, "values.1") == 20

    def test_missing_path_returns_none(self) -> None:
        assert resolve_path(RUNS["r1"], "validation.does_not_exist") is None

    def test_descending_through_a_scalar_returns_none(self) -> None:
        assert resolve_path(RUNS["r1"], "training_rows.deeper") is None


class TestRendering:
    def test_substitutes_from_the_run_record(self) -> None:
        result = render_template("FIT={{run:r1.validation.free_run_fit}}", runs=RUNS)
        assert "97.8612" in result.text
        assert result.fully_resolved
        assert result.bindings[0].run_id == "r1"
        assert result.bindings[0].path == "validation.free_run_fit"

    def test_booleans_render_readably(self) -> None:
        result = render_template("稳定性={{run:r1.validation.stable}}", runs=RUNS)
        assert "是" in result.text

    def test_an_unresolvable_placeholder_is_marked_not_blanked(self) -> None:
        """A silently dropped figure is more dangerous than a visibly missing one."""

        result = render_template("值={{run:r1.nope}}", runs=RUNS)
        assert "[未解析数值:r1.nope]" in result.text
        assert not result.fully_resolved
        assert result.unresolved

    def test_every_rendered_number_has_a_binding(self) -> None:
        template = (
            "{{run:r1.validation.free_run_fit}} / {{run:r1.validation.one_step_fit}}"
            " / {{run:r1.training_rows}}"
        )
        result = render_template(template, runs=RUNS)
        assert len(result.bindings) == 3
        assert all(binding.resolved for binding in result.bindings)

    def test_rendered_output_would_now_fail_numeral_validation(self) -> None:
        """The rendered document contains real numbers; only the *draft* must not."""

        result = render_template("FIT={{run:r1.validation.free_run_fit}}", runs=RUNS)
        assert validate_draft(result.text) != []


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'report.db'}")
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


def run_pipeline(client: TestClient) -> str:
    """Drive the real pipeline so the report has genuine runs to cite."""

    generated = client.post(
        "/api/v1/simulation/generate",
        json={"scenario": "S2", "n_steps": 2500, "seed": 12, "input_count": 2},
    )
    assert generated.status_code == 201, generated.text
    version_id = generated.json()["data"]["version_id"]

    segment = client.post(
        "/api/v1/preprocessing/segment",
        json={
            "version_id": version_id,
            "input_columns": ["u1", "u2"],
            "output_column": "y",
            "window_size": 60,
            "max_segments": 6,
        },
    )
    assert segment.status_code == 202, segment.text

    fitted = client.post(
        "/api/v1/modeling/arx/fit",
        json={
            "version_id": version_id,
            "input_columns": ["u1", "u2"],
            "output_column": "y",
            "na": 2,
            "nb": [2, 2],
            "delays": [3, 8],
        },
    )
    assert fitted.status_code == 200, fitted.text
    return version_id


class TestReportApi:
    def test_report_cites_real_runs_and_binds_every_number(self, client: TestClient) -> None:
        version_id = run_pipeline(client)
        response = client.post("/api/v1/reports/generate", json={"version_id": version_id})
        assert response.status_code == 200, response.text
        data = response.json()["data"]

        assert data["bindings"], "the report must bind at least one figure to a run"
        assert data["fully_resolved"] is True
        assert data["unresolved"] == []
        for binding in data["bindings"]:
            assert binding["run_id"]
            assert binding["resolved"] is True
        assert any(section["key"] == "selection" for section in data["sections"])
        assert any(section["key"] == "model" for section in data["sections"])

    def test_report_body_contains_no_placeholder_left_over(self, client: TestClient) -> None:
        version_id = run_pipeline(client)
        data = client.post("/api/v1/reports/generate", json={"version_id": version_id}).json()[
            "data"
        ]
        assert "{{" not in data["markdown"]

    def test_report_artifact_is_written_to_disk(self, client: TestClient, tmp_path: Path) -> None:
        version_id = run_pipeline(client)
        data = client.post("/api/v1/reports/generate", json={"version_id": version_id}).json()[
            "data"
        ]
        assert (tmp_path / data["artifact_uri"]).is_file()

    def test_report_without_runs_is_refused(self, client: TestClient) -> None:
        response = client.post("/api/v1/reports/generate", json={"version_id": str(uuid4())})
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "REPORT_NO_RUNS"


class TestExportApi:
    def test_export_writes_the_selected_rows_and_a_manifest(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        version_id = run_pipeline(client)
        response = client.post(
            "/api/v1/delivery/export",
            json={
                "version_id": version_id,
                "input_columns": ["u1", "u2"],
                "output_column": "y",
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]

        assert data["exported_rows"] > 0
        assert data["exported_rows"] < data["source_rows"], "export must be a real subset"
        assert 0 < data["coverage_ratio"] < 1

        csv_path = tmp_path / data["csv_uri"]
        assert csv_path.is_file()
        with csv_path.open(encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        assert rows[0] == data["columns"]
        assert len(rows) - 1 == data["exported_rows"]

        manifest = json.loads((tmp_path / data["manifest_uri"]).read_text(encoding="utf-8"))
        assert manifest["version_id"] == version_id
        assert manifest["exported_rows"] == data["exported_rows"]

    def test_explicit_indices_are_honoured(self, client: TestClient) -> None:
        version_id = run_pipeline(client)
        response = client.post(
            "/api/v1/delivery/export",
            json={
                "version_id": version_id,
                "input_columns": ["u1", "u2"],
                "output_column": "y",
                "sample_indices": [100, 101, 102, 103],
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["exported_rows"] == 4

    def test_export_without_a_selection_is_refused(self, client: TestClient) -> None:
        generated = client.post(
            "/api/v1/simulation/generate",
            json={"scenario": "S1", "n_steps": 1200, "seed": 3, "input_count": 1},
        )
        version_id = generated.json()["data"]["version_id"]
        response = client.post(
            "/api/v1/delivery/export",
            json={"version_id": version_id, "input_columns": ["u1"], "output_column": "y"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "EXPORT_NO_SELECTION"
