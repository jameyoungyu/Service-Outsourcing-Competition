"""Tests for prewhitened delay estimation and collinearity diagnostics (phase 6)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import numpy as np
import pytest
from algorithms.identifiability.collinearity import (
    analyze_collinearity,
    design_condition_number,
    variance_inflation_factors,
)
from algorithms.identifiability.delay import (
    apply_ar_filter,
    estimate_delays,
    fit_ar_model,
    prewhitened_cross_correlation,
    rank_candidates,
)
from algorithms.identifiability.regressor import IdentifiabilityError
from app.core.config import Settings
from app.core.db import get_session
from app.main import create_app
from app.models import Base
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

AR = [-1.3, 0.42]
B = {"u1": [0.45, 0.15], "u2": [0.25, 0.08]}
TRUE_DELAYS = {"u1": 5, "u2": 12}


def correlated_input(n_samples: int, generator: np.random.Generator, *, hold: int) -> np.ndarray:
    """Piecewise-constant input: strongly autocorrelated, like a real operator's moves."""

    values = np.empty(n_samples, dtype=float)
    for start in range(0, n_samples, hold):
        values[start : start + hold] = generator.uniform(-1.5, 1.5)
    return values


def simulate(inputs: dict[str, np.ndarray], *, noise: float, seed: int) -> np.ndarray:
    generator = np.random.default_rng(seed)
    n_samples = len(next(iter(inputs.values())))
    output = np.zeros(n_samples, dtype=float)
    history = max(len(AR), max(TRUE_DELAYS[c] + len(B[c]) - 1 for c in inputs))
    for index in range(history, n_samples):
        value = -sum(AR[lag - 1] * output[index - lag] for lag in range(1, len(AR) + 1))
        for column, signal in inputs.items():
            for lag, coefficient in enumerate(B[column]):
                value += coefficient * signal[index - TRUE_DELAYS[column] - lag]
        output[index] = value + generator.normal(0.0, noise)
    return output


def scenario(*, n_samples: int = 5000, noise: float = 0.02, seed: int = 17):
    generator = np.random.default_rng(seed)
    inputs = {
        "u1": correlated_input(n_samples, generator, hold=40),
        "u2": correlated_input(n_samples, generator, hold=55),
    }
    return inputs, simulate(inputs, noise=noise, seed=seed)


class TestPrewhitening:
    def test_ar_model_recovers_a_known_process(self) -> None:
        generator = np.random.default_rng(3)
        n_samples = 6000
        values = np.zeros(n_samples)
        for index in range(2, n_samples):
            values[index] = (
                0.6 * values[index - 1] - 0.2 * values[index - 2] + generator.normal(0, 1.0)
            )
        coefficients, order = fit_ar_model(values, max_order=10)
        assert order >= 2
        # A(q) = 1 + a1 q^-1 + a2 q^-2 must invert the generating recursion.
        assert coefficients[0] == pytest.approx(-0.6, abs=0.08)
        assert coefficients[1] == pytest.approx(0.2, abs=0.08)

    def test_filtering_whitens_an_autocorrelated_signal(self) -> None:
        generator = np.random.default_rng(4)
        signal = correlated_input(6000, generator, hold=30)
        coefficients, _ = fit_ar_model(signal, max_order=20)
        filtered = apply_ar_filter(signal, coefficients)

        def lag1(values: np.ndarray) -> float:
            centered = values - values.mean()
            return float(np.dot(centered[:-1], centered[1:]) / np.dot(centered, centered))

        assert abs(lag1(filtered)) < abs(lag1(signal))
        assert abs(lag1(filtered)) < 0.2

    def test_prewhitening_beats_raw_cross_correlation_on_the_delay_peak(self) -> None:
        """The raw peak is biased by the input's own autocovariance; prewhitening is not."""

        inputs, output = scenario()
        signal = inputs["u1"]

        correlations, order = prewhitened_cross_correlation(signal, output, max_lag=40)
        assert order >= 1
        prewhitened_peak = int(np.argmax(np.abs(correlations)))

        centered_input = signal - signal.mean()
        centered_output = output - output.mean()
        raw = np.array(
            [
                float(
                    np.dot(centered_input[: len(signal) - lag], centered_output[lag:])
                    / (
                        np.linalg.norm(centered_input[: len(signal) - lag])
                        * np.linalg.norm(centered_output[lag:])
                    )
                )
                for lag in range(41)
            ]
        )
        raw_peak = int(np.argmax(np.abs(raw)))

        truth = TRUE_DELAYS["u1"]
        assert abs(prewhitened_peak - truth) <= abs(raw_peak - truth)
        assert abs(prewhitened_peak - truth) <= 2

    def test_rank_candidates_returns_ordered_local_peaks(self) -> None:
        correlations = np.array([0.1, 0.9, 0.2, 0.05, 0.6, 0.1])
        candidates = rank_candidates(correlations, top_k=2, sample_count=1000)
        assert [candidate.lag for candidate in candidates] == [1, 4]
        assert candidates[0].correlation == pytest.approx(0.9)

    def test_negative_max_lag_is_rejected(self) -> None:
        with pytest.raises(IdentifiabilityError):
            prewhitened_cross_correlation(np.zeros(100), np.zeros(100), max_lag=-1)


class TestDelayRefinement:
    def test_recovers_both_true_delays(self) -> None:
        inputs, output = scenario()
        result = estimate_delays(inputs=inputs, output=output, max_lag=30, top_k=3)
        for column, truth in TRUE_DELAYS.items():
            assert abs(result.refined_delays[column] - truth) <= 2, (
                f"{column}: got {result.refined_delays[column]}, expected ~{truth}"
            )

    def test_refinement_reports_a_real_validation_fit(self) -> None:
        inputs, output = scenario()
        result = estimate_delays(inputs=inputs, output=output, max_lag=30)
        assert np.isfinite(result.validation_fit)
        assert result.validation_fit > 50.0

    def test_short_record_is_rejected_rather_than_guessed(self) -> None:
        inputs = {"u1": np.zeros(60), "u2": np.zeros(60)}
        with pytest.raises(IdentifiabilityError) as error:
            estimate_delays(inputs=inputs, output=np.zeros(60), max_lag=50)
        assert error.value.code == "INSUFFICIENT_ROWS"


class TestCollinearity:
    def _inputs(self) -> dict[str, np.ndarray]:
        generator = np.random.default_rng(21)
        base = generator.normal(size=2000)
        return {
            "u1": base,
            "u2": 0.98 * base + generator.normal(0, 0.05, 2000),  # near-duplicate of u1
            "u3": generator.normal(size=2000),
        }

    def test_detects_the_redundant_pair(self) -> None:
        result = analyze_collinearity(inputs=self._inputs())
        pairs = {tuple(sorted((pair.left, pair.right))) for pair in result.correlated_pairs}
        assert ("u1", "u2") in pairs
        assert any(set(group) == {"u1", "u2"} for group in result.groups)

    def test_vif_is_large_for_the_redundant_pair_and_small_for_the_independent_one(self) -> None:
        factors = variance_inflation_factors(("u1", "u2", "u3"), self._inputs())
        assert factors["u1"] > 10
        assert factors["u2"] > 10
        assert factors["u3"] < 2

    def test_condition_number_is_scale_invariant(self) -> None:
        inputs = self._inputs()
        rescaled = {
            name: values * (1000.0 if name == "u3" else 1.0) for name, values in inputs.items()
        }
        assert design_condition_number(("u1", "u2", "u3"), inputs) == pytest.approx(
            design_condition_number(("u1", "u2", "u3"), rescaled), rel=1e-6
        )

    def test_advice_keeps_one_representative_and_drops_the_other(self) -> None:
        result = analyze_collinearity(inputs=self._inputs())
        actions = {item.variable: item.action for item in result.advice}
        assert actions["u3"] == "keep"
        assert {actions["u1"], actions["u2"]} == {"keep", "drop"}

    def test_independent_inputs_produce_no_groups(self) -> None:
        generator = np.random.default_rng(31)
        inputs = {name: generator.normal(size=1500) for name in ("u1", "u2", "u3")}
        result = analyze_collinearity(inputs=inputs)
        assert result.groups == ()
        assert all(item.action == "keep" for item in result.advice)

    def test_requires_two_inputs(self) -> None:
        with pytest.raises(IdentifiabilityError):
            analyze_collinearity(inputs={"u1": np.zeros(100)})

    def test_spearman_catches_a_monotone_nonlinear_pair_that_pearson_understates(self) -> None:
        base = np.linspace(0.1, 5.0, 1500)
        inputs = {"u1": base, "u2": np.exp(base)}
        result = analyze_collinearity(inputs=inputs, correlation_threshold=0.99)
        assert abs(result.spearman[0][1]) > abs(result.pearson[0][1])
        assert result.spearman[0][1] == pytest.approx(1.0, abs=1e-6)


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'phase6.db'}")
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


def generate_benchmark(client: TestClient, scenario_name: str = "S2") -> str:
    response = client.post(
        "/api/v1/simulation/generate",
        json={"scenario": scenario_name, "n_steps": 4000, "seed": 7, "input_count": 2},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["version_id"]


class TestPhase6Api:
    def test_delay_endpoint_recovers_the_benchmark_delays(self, api_client: TestClient) -> None:
        version_id = generate_benchmark(api_client)
        response = api_client.post(
            "/api/v1/preprocessing/delay",
            json={
                "version_id": version_id,
                "input_columns": ["u1", "u2"],
                "output_column": "y",
                "max_lag": 30,
            },
        )
        assert response.status_code == 202, response.text
        data = response.json()["data"]

        # S2 ground truth from simulation_service._scenario_parameters: u1 -> 3, u2 -> 8.
        assert abs(data["best_delays"]["u1"] - 3) <= 2
        assert abs(data["best_delays"]["u2"] - 8) <= 2
        assert data["validation_fit"] is not None
        assert data["prewhitening_orders"]["u1"] >= 1
        assert len(data["correlations"]["u1"]) == 31

    def test_collinearity_endpoint_flags_the_s5_redundant_input(
        self, api_client: TestClient
    ) -> None:
        version_id = generate_benchmark(api_client, "S5")
        response = api_client.post(
            "/api/v1/preprocessing/collinearity",
            json={
                "version_id": version_id,
                "input_columns": ["u1", "u2"],
                "correlation_threshold": 0.9,
            },
        )
        assert response.status_code == 202, response.text
        data = response.json()["data"]

        # S5 builds u2 as 0.97*u1 plus a little noise, so the pair must be flagged.
        assert data["correlated_groups"], "S5's redundant input pair must be grouped"
        assert abs(data["matrix"][0][1]) > 0.9
        assert {item["action"] for item in data["recommendations"]} & {"keep", "drop"}

    def test_delay_rejects_an_unknown_column(self, api_client: TestClient) -> None:
        version_id = generate_benchmark(api_client)
        response = api_client.post(
            "/api/v1/preprocessing/delay",
            json={
                "version_id": version_id,
                "input_columns": ["does_not_exist"],
                "output_column": "y",
            },
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_DATASET_SCHEMA"
