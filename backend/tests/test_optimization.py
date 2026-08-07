"""Tests for the closed loop: cache, fingerprints, objective and strategy memory."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from algorithms.pipeline.cache import LineageCache, canonical_json, stage_key
from algorithms.pipeline.fingerprint import build_fingerprint, fingerprint_distance
from app.core.config import Settings
from app.core.db import get_session
from app.main import create_app
from app.models import Base
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class TestCanonicalKeys:
    def test_key_ignores_dict_ordering(self) -> None:
        assert canonical_json({"a": 1, "b": 2}) == canonical_json({"b": 2, "a": 1})

    def test_key_ignores_float_noise_below_precision(self) -> None:
        left = stage_key(
            parent_key="p", tool_name="t", tool_version="1", parameters={"x": 0.1}
        )
        right = stage_key(
            parent_key="p", tool_name="t", tool_version="1", parameters={"x": 0.1 + 1e-15}
        )
        assert left == right

    def test_key_changes_with_a_meaningful_parameter_change(self) -> None:
        left = stage_key(parent_key="p", tool_name="t", tool_version="1", parameters={"x": 0.1})
        right = stage_key(parent_key="p", tool_name="t", tool_version="1", parameters={"x": 0.2})
        assert left != right

    def test_key_changes_with_tool_version(self) -> None:
        left = stage_key(parent_key="p", tool_name="t", tool_version="1", parameters={})
        right = stage_key(parent_key="p", tool_name="t", tool_version="2", parameters={})
        assert left != right

    def test_key_changes_with_parent(self) -> None:
        left = stage_key(parent_key="a", tool_name="t", tool_version="1", parameters={})
        right = stage_key(parent_key="b", tool_name="t", tool_version="1", parameters={})
        assert left != right


class TestLineageCache:
    def test_second_lookup_is_a_hit_and_does_not_recompute(self) -> None:
        cache = LineageCache()
        calls = {"count": 0}

        def compute() -> int:
            calls["count"] += 1
            return 42

        first, cached_first = cache.get_or_compute("k", compute)
        second, cached_second = cache.get_or_compute("k", compute)

        assert (first, second) == (42, 42)
        assert cached_first is False
        assert cached_second is True
        assert calls["count"] == 1
        assert cache.hit_rate == 0.5

    def test_eviction_keeps_the_table_bounded(self) -> None:
        cache = LineageCache(max_entries=2)
        for index in range(5):
            cache.get_or_compute(f"k{index}", lambda index=index: index)
        assert cache.statistics()["entries"] == 2

    def test_statistics_report_hits_and_misses(self) -> None:
        cache = LineageCache()
        cache.get_or_compute("a", lambda: 1)
        cache.get_or_compute("a", lambda: 1)
        cache.get_or_compute("b", lambda: 2)
        stats = cache.statistics()
        assert stats["hits"] == 1
        assert stats["misses"] == 2
        assert stats["lookups"] == 3


def make_series(*, n_samples: int = 3000, noise: float = 0.02, seed: int = 3):  # type: ignore[no-untyped-def]
    from app.services.version_data import VersionSeries

    generator = np.random.default_rng(seed)
    inputs = {}
    for offset, name in enumerate(("u1", "u2")):
        values = np.zeros(n_samples, dtype=float)
        hold = 13 + offset * 6
        for start in range(0, n_samples, hold):
            values[start : start + hold] = generator.uniform(-1.5, 1.5)
        inputs[name] = values

    ar = [-1.35, 0.45]
    b = {"u1": [0.4, 0.14], "u2": [0.2, 0.07]}
    nk = {"u1": 3, "u2": 6}
    output = np.zeros(n_samples, dtype=float)
    history = max(len(ar), max(nk[c] + len(b[c]) - 1 for c in inputs))
    for index in range(history, n_samples):
        value = -sum(ar[lag - 1] * output[index - lag] for lag in range(1, len(ar) + 1))
        for column, signal in inputs.items():
            for lag, coefficient in enumerate(b[column]):
                value += coefficient * signal[index - nk[column] - lag]
        output[index] = value + generator.normal(0.0, noise)

    return VersionSeries(
        dataset_id=uuid4(),
        version_id=uuid4(),
        dataset_name="opt-test",
        origin="simulation",
        timestamps=[],
        values={**inputs, "y": output},
        declared_inputs=tuple(inputs),
        declared_output="y",
        sample_period_seconds=1.0,
    )


class TestFingerprint:
    def test_similar_datasets_are_close(self) -> None:
        left = build_fingerprint(
            inputs={k: v for k, v in make_series(seed=1).values.items() if k != "y"},
            output=make_series(seed=1).values["y"],
        )
        right = build_fingerprint(
            inputs={k: v for k, v in make_series(seed=2).values.items() if k != "y"},
            output=make_series(seed=2).values["y"],
        )
        assert fingerprint_distance(left.vector, right.vector) < 0.35

    def test_a_much_noisier_dataset_is_further_away(self) -> None:
        clean = make_series(noise=0.01, seed=5)
        noisy = make_series(noise=3.0, seed=5)
        left = build_fingerprint(
            inputs={k: v for k, v in clean.values.items() if k != "y"},
            output=clean.values["y"],
        )
        right = build_fingerprint(
            inputs={k: v for k, v in noisy.values.items() if k != "y"},
            output=noisy.values["y"],
        )
        assert fingerprint_distance(left.vector, right.vector) > 0.1

    def test_vector_length_is_stable(self) -> None:
        from algorithms.pipeline.fingerprint import FINGERPRINT_FIELDS

        series = make_series()
        fingerprint = build_fingerprint(
            inputs={k: v for k, v in series.values.items() if k != "y"},
            output=series.values["y"],
        )
        assert len(fingerprint.vector) == len(FINGERPRINT_FIELDS)

    def test_mismatched_vectors_are_infinitely_far(self) -> None:
        assert fingerprint_distance([1.0, 2.0], [1.0]) == float("inf")


class TestObjective:
    def _result(self, **overrides: object):  # type: ignore[no-untyped-def]
        from app.schemas.modeling import ArxFitRequest
        from app.services.modeling_service import fit_arx_core

        series = make_series()
        payload = ArxFitRequest(
            version_id=series.version_id,
            input_columns=["u1", "u2"],
            output_column="y",
            na=2,
            nb={"u1": 2, "u2": 2},
            delays={"u1": 3, "u2": 6},
            **overrides,  # type: ignore[arg-type]
        )
        return fit_arx_core(
            inputs={k: v for k, v in series.values.items() if k != "y"},
            output=series.values["y"],
            payload=payload,
            input_columns=["u1", "u2"],
        )

    def test_a_good_model_scores_positively(self) -> None:
        from app.services.optimization_service import objective_value

        value, breakdown = objective_value(self._result())
        assert value > 0
        assert breakdown["val_free_run_fit"] > 80

    def test_objective_is_driven_by_free_run_not_one_step(self) -> None:
        from app.services.optimization_service import objective_value

        good = self._result()
        starved = self._result(training_sample_indices=list(range(20, 260)))
        good_value, good_breakdown = objective_value(good)
        starved_value, starved_breakdown = objective_value(starved)

        assert good_value > starved_value
        free_run_gap = good_breakdown["val_free_run_fit"] - starved_breakdown["val_free_run_fit"]
        one_step_gap = abs(
            (good_breakdown["val_one_step_fit"] or 0)
            - (starved_breakdown["val_one_step_fit"] or 0)
        )
        assert free_run_gap > one_step_gap


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'optimize.db'}")
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


def generate(client: TestClient, *, seed: int = 4, scenario: str = "S2") -> str:
    response = client.post(
        "/api/v1/simulation/generate",
        json={"scenario": scenario, "n_steps": 2000, "seed": seed, "input_count": 2},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["version_id"]


class TestOptimizationApi:
    def test_closed_loop_runs_and_reports_cache_statistics(self, client: TestClient) -> None:
        version_id = generate(client)
        started = client.post(
            "/api/v1/optimization/optuna/start",
            json={
                "version_id": version_id,
                "input_columns": ["u1", "u2"],
                "output_column": "y",
                "max_trials": 12,
                "random_seed": 7,
            },
        )
        assert started.status_code == 202, started.text
        study_id = started.json()["data"]["study_id"]

        status = client.get(f"/api/v1/optimization/optuna/{study_id}/status")
        assert status.status_code == 200, status.text
        data = status.json()["data"]

        assert len(data["trials"]) == 12
        assert data["best_value"] is not None
        assert data["best_params"]
        assert data["statistics"]["total_trials"] == 12
        assert data["statistics"]["lookups"] > 0

    def test_the_expensive_stage_is_amortised_across_the_structure_sweep(
        self, client: TestClient
    ) -> None:
        """Selection is the expensive stage; every trial must reuse one across many fits.

        This is where the closed-loop saving actually comes from. Measured separately, the
        content-addressed cache hits only ~1.7% of the time in a flat TPE search because a
        five-dimensional head almost never repeats, so the staged design carries the win
        and the assertion is written against that, not against the cache.
        """

        version_id = generate(client)
        started = client.post(
            "/api/v1/optimization/optuna/start",
            json={
                "version_id": version_id,
                "input_columns": ["u1", "u2"],
                "output_column": "y",
                "max_trials": 6,
                "random_seed": 17,
            },
        )
        study_id = started.json()["data"]["study_id"]
        stats = client.get(f"/api/v1/optimization/optuna/{study_id}/status").json()["data"][
            "statistics"
        ]

        assert stats["structure_evaluations"] > stats["selection_computations"]
        assert stats["evaluations_per_selection"] > 5.0

    def test_convergence_curve_is_monotone_non_decreasing(self, client: TestClient) -> None:
        version_id = generate(client)
        started = client.post(
            "/api/v1/optimization/optuna/start",
            json={
                "version_id": version_id,
                "input_columns": ["u1", "u2"],
                "output_column": "y",
                "max_trials": 10,
                "random_seed": 3,
            },
        )
        study_id = started.json()["data"]["study_id"]
        curve = client.get(f"/api/v1/optimization/optuna/{study_id}/status").json()["data"][
            "best_curve"
        ]
        seen = [value for value in curve if value is not None]
        assert seen == sorted(seen), "the best-so-far curve can never go down"

    def test_failed_trials_are_persisted_not_hidden(self, client: TestClient) -> None:
        version_id = generate(client)
        started = client.post(
            "/api/v1/optimization/optuna/start",
            json={
                "version_id": version_id,
                "input_columns": ["u1", "u2"],
                "output_column": "y",
                "max_trials": 14,
                "random_seed": 11,
            },
        )
        study_id = started.json()["data"]["study_id"]
        data = client.get(f"/api/v1/optimization/optuna/{study_id}/status").json()["data"]
        states = {trial["state"] for trial in data["trials"]}
        assert states <= {"complete", "pruned", "failed"}
        assert data["statistics"]["total_trials"] == len(data["trials"])

    def test_second_study_on_a_different_dataset_is_warm_started(
        self, client: TestClient
    ) -> None:
        """The self-evolving path: a finished study leaves a reusable prior behind."""

        first_version = generate(client, seed=4)
        first = client.post(
            "/api/v1/optimization/optuna/start",
            json={
                "version_id": first_version,
                "input_columns": ["u1", "u2"],
                "output_column": "y",
                "max_trials": 10,
                "random_seed": 5,
            },
        )
        assert first.status_code == 202, first.text

        second_version = generate(client, seed=9)
        second = client.post(
            "/api/v1/optimization/optuna/start",
            json={
                "version_id": second_version,
                "input_columns": ["u1", "u2"],
                "output_column": "y",
                "max_trials": 10,
                "random_seed": 5,
            },
        )
        assert second.status_code == 202, second.text
        second_id = second.json()["data"]["study_id"]
        data = client.get(f"/api/v1/optimization/optuna/{second_id}/status").json()["data"]

        assert data["warm_started_from"] is not None, (
            "a similar previous study should supply a warm start"
        )
        assert data["statistics"]["warm_start_trials"] > 0

    def test_status_of_an_unknown_study_returns_404(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/optimization/optuna/{uuid4()}/status")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "OPTIMIZATION_STUDY_NOT_FOUND"

    def test_unknown_version_returns_404(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/optimization/optuna/start",
            json={
                "version_id": str(uuid4()),
                "input_columns": ["u1"],
                "output_column": "y",
                "max_trials": 2,
            },
        )
        assert response.status_code == 404
