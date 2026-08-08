"""Tests for the in-product self-benchmark (phase 11)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from app.core.config import Settings
from app.core.db import get_session
from app.main import create_app
from app.models import Base
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bench.db'}")
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


def run(client: TestClient, **overrides: object) -> dict:
    body: dict[str, object] = {"scenarios": ["S3", "S6"], "n_samples": 3000}
    body.update(overrides)
    response = client.post("/api/v1/benchmark/run", json=body)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def rows(data: dict, key: str) -> list[dict]:
    experiment = next(item for item in data["experiments"] if item["key"] == key)
    return experiment["rows"]


class TestSelfBenchmark:
    def test_runs_all_three_ablations(self, client: TestClient) -> None:
        data = run(client)
        assert {item["key"] for item in data["experiments"]} == {"selection", "metric", "delay"}
        assert data["duration_ms"] > 0

    def test_selection_ablation_covers_every_strategy_and_scenario(
        self, client: TestClient
    ) -> None:
        data = run(client)
        selection = rows(data, "selection")
        assert {row["strategy"] for row in selection} == {"full", "energy", "weighted", "ids"}
        assert {row["scenario"] for row in selection} == {"S3", "S6"}

    def test_selection_uses_a_real_subset(self, client: TestClient) -> None:
        data = run(client)
        for row in rows(data, "selection"):
            if row["strategy"] == "full":
                continue
            assert row["metrics"]["coverage_ratio"] < 0.5

    def test_energy_heuristic_degrades_under_heterogeneous_excitation(
        self, client: TestClient
    ) -> None:
        """S6 exists to expose this; if it stopped happening the claim would be stale."""

        data = run(client)
        by_key = {
            (row["scenario"], row["strategy"]): row["metrics"] for row in rows(data, "selection")
        }
        energy = by_key[("S6", "energy")]
        ids = by_key[("S6", "ids")]
        assert ids["parameter_error"] < energy["parameter_error"]
        assert ids["free_run_fit"] > energy["free_run_fit"]

    def test_the_full_weighted_score_fails_the_same_way_energy_does(
        self, client: TestClient
    ) -> None:
        """The comparison must not rest on a straw man.

        ``weighted`` is the ``ALG-0.1`` §6.2 score at its published weights — anomaly,
        missing, SNR and response-association terms included. It is the baseline a careful
        literal implementation of the task statement produces. On heterogeneous excitation
        it still lands in energy's failure mode, because a per-window score has no way to
        represent redundancy against windows already chosen.
        """

        data = run(client)
        by_key = {
            (row["scenario"], row["strategy"]): row["metrics"] for row in rows(data, "selection")
        }
        weighted = by_key[("S6", "weighted")]
        energy = by_key[("S6", "energy")]
        ids = by_key[("S6", "ids")]

        assert ids["parameter_error"] < weighted["parameter_error"] / 2
        # Same failure mode, not merely a worse score: both leave the design rank-deficient.
        assert weighted["rank_deficient"] == 1.0
        assert energy["rank_deficient"] == 1.0
        assert ids["rank_deficient"] == 0.0
        assert abs(weighted["parameter_error"] - energy["parameter_error"]) < 0.05

    def test_a_singular_design_reaches_the_client_as_a_number(self) -> None:
        """``float("inf")`` serialises to JSON ``null``, which would blank the worst result."""

        import numpy as np
        from app.services.benchmark_service import CONDITION_CEILING, _condition, _rank_deficient

        singular = np.array([[1.0, 2.0], [2.0, 4.0], [3.0, 6.0]])
        assert _condition(singular) == CONDITION_CEILING
        assert _rank_deficient(singular) == 1.0
        assert _rank_deficient(np.eye(3)) == 0.0

    def test_the_weighted_score_is_allowed_to_win_on_homogeneous_excitation(
        self, client: TestClient
    ) -> None:
        """S3 is the case where D-optimal has nothing to offer, and the table says so.

        Every dynamic window in S3 carries the same information, so modelling redundancy
        buys nothing and ranking by quality is the right thing to do. Asserting that
        D-optimal wins everywhere would be asserting something the measurements do not
        support; the honest invariant is that no strategy collapses.
        """

        data = run(client)
        by_key = {
            (row["scenario"], row["strategy"]): row["metrics"] for row in rows(data, "selection")
        }
        for strategy in ("full", "energy", "weighted", "ids"):
            metrics = by_key[("S3", strategy)]
            assert metrics["parameter_error"] < 0.15
            assert metrics["free_run_fit"] > 80.0

    def test_selection_matches_full_data_on_the_heterogeneous_case(
        self, client: TestClient
    ) -> None:
        data = run(client)
        by_key = {
            (row["scenario"], row["strategy"]): row["metrics"] for row in rows(data, "selection")
        }
        full = by_key[("S6", "full")]
        ids = by_key[("S6", "ids")]
        assert ids["free_run_fit"] > full["free_run_fit"] - 5.0
        assert ids["coverage_ratio"] < full["coverage_ratio"] / 3

    def test_free_run_discriminates_better_than_one_step(self, client: TestClient) -> None:
        data = run(client)
        by_key = {
            (row["scenario"], row["strategy"]): row["metrics"] for row in rows(data, "metric")
        }
        for scenario in ("S3", "S6"):
            good = by_key[(scenario, "well_fitted")]
            starved = by_key[(scenario, "starved")]
            one_step_spread = abs(good["one_step_fit"] - starved["one_step_fit"])
            free_run_spread = abs(good["free_run_fit"] - starved["free_run_fit"])
            assert free_run_spread > one_step_spread, scenario

    def test_delay_ablation_reports_both_estimators_against_truth(self, client: TestClient) -> None:
        data = run(client)
        delay = rows(data, "delay")
        assert delay
        for row in delay:
            assert {"true_delay", "raw_error", "prewhitened_error"} <= set(row["metrics"])

    def test_prewhitening_wins_on_balance_without_claiming_a_sweep(
        self, client: TestClient
    ) -> None:
        """It is better on most channels, not all; the note must say so honestly."""

        data = run(client)
        delay = rows(data, "delay")
        better = sum(
            1 for row in delay if row["metrics"]["prewhitened_error"] < row["metrics"]["raw_error"]
        )
        worse = sum(
            1 for row in delay if row["metrics"]["prewhitened_error"] > row["metrics"]["raw_error"]
        )
        assert better > worse
        experiment = next(item for item in data["experiments"] if item["key"] == "delay")
        assert any("更差的通道数" in note for note in experiment["notes"])

    def test_a_single_scenario_still_works(self, client: TestClient) -> None:
        data = run(client, scenarios=["S6"])
        assert {row["scenario"] for row in rows(data, "selection")} == {"S6"}

    def test_result_is_persisted_for_the_report_to_cite(self, client: TestClient) -> None:
        data = run(client)
        assert data["benchmark_id"]

    def test_an_unknown_scenario_is_rejected_by_the_schema(self, client: TestClient) -> None:
        response = client.post("/api/v1/benchmark/run", json={"scenarios": ["S99"]})
        assert response.status_code == 422
