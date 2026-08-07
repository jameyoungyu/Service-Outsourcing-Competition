"""Tests for control-relevant ARX identification and acceptance (phase 7)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from app.core.config import Settings
from app.core.db import get_session
from app.main import create_app
from app.models import Base
from app.schemas.modeling import ArxFitRequest
from app.services.modeling_service import ModelingDomainError, fit_arx_core
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

AR = [-1.4, 0.48]
B = {"u1": [0.36, 0.12], "u2": [0.18, 0.06]}
NK = {"u1": 3, "u2": 8}


def make_inputs(n_samples: int, seed: int = 5) -> dict[str, np.ndarray]:
    generator = np.random.default_rng(seed)
    signals = {}
    for offset, column in enumerate(B):
        values = np.empty(n_samples, dtype=float)
        hold = 11 + offset * 7
        for start in range(0, n_samples, hold):
            values[start : start + hold] = generator.uniform(-1.5, 1.5)
        signals[column] = values
    return signals


def simulate(inputs: dict[str, np.ndarray], *, noise: float, seed: int = 9) -> np.ndarray:
    generator = np.random.default_rng(seed)
    n_samples = len(next(iter(inputs.values())))
    output = np.zeros(n_samples, dtype=float)
    history = max(len(AR), max(NK[c] + len(B[c]) - 1 for c in inputs))
    for index in range(history, n_samples):
        value = -sum(AR[lag - 1] * output[index - lag] for lag in range(1, len(AR) + 1))
        for column, signal in inputs.items():
            for lag, coefficient in enumerate(B[column]):
                value += coefficient * signal[index - NK[column] - lag]
        output[index] = value + (generator.normal(0.0, noise) if noise else 0.0)
    return output


def request(**overrides: object) -> ArxFitRequest:
    base: dict[str, object] = {
        "version_id": uuid4(),
        "input_columns": list(B),
        "output_column": "y",
        "na": len(AR),
        "nb": {c: len(v) for c, v in B.items()},
        "delays": dict(NK),
        "estimator": "ols",
    }
    base.update(overrides)
    return ArxFitRequest(**base)  # type: ignore[arg-type]


def fit(inputs: dict[str, np.ndarray], output: np.ndarray, **overrides: object):  # type: ignore[no-untyped-def]
    return fit_arx_core(
        inputs=inputs,
        output=output,
        payload=request(**overrides),
        input_columns=list(B),
    )


class TestIdentification:
    def test_recovers_parameters_from_noiseless_data(self) -> None:
        inputs = make_inputs(3000)
        result = fit(inputs, simulate(inputs, noise=0.0))
        assert result.a_coefficients[0] == pytest.approx(AR[0], abs=1e-6)
        assert result.a_coefficients[1] == pytest.approx(AR[1], abs=1e-6)
        for column, truth in B.items():
            assert result.b_coefficients[column] == pytest.approx(truth, abs=1e-6)

    def test_free_run_is_perfect_on_noiseless_data(self) -> None:
        inputs = make_inputs(3000)
        result = fit(inputs, simulate(inputs, noise=0.0))
        assert result.metrics.val_free_run_fit is not None
        assert result.metrics.val_free_run_fit > 99.99
        assert result.validation.fit_gap == pytest.approx(0.0, abs=0.01)

    def test_reports_both_one_step_and_free_run_per_partition(self) -> None:
        inputs = make_inputs(3000)
        result = fit(inputs, simulate(inputs, noise=0.03))
        for value in (
            result.metrics.train_fit,
            result.metrics.val_fit,
            result.metrics.test_fit,
            result.metrics.train_free_run_fit,
            result.metrics.val_free_run_fit,
            result.metrics.test_free_run_fit,
        ):
            assert value is not None

    def test_one_step_fit_hides_a_degraded_model_that_free_run_exposes(self) -> None:
        """The whole reason free-run is the primary metric, asserted on real numbers."""

        inputs = make_inputs(4000)
        output = simulate(inputs, noise=0.03)
        good = fit(inputs, output)
        # Starve the fit: identify using only a short, weakly informative slice.
        starved = fit(
            inputs,
            output,
            training_sample_indices=list(range(20, 220)),
        )

        one_step_gap = abs((good.metrics.val_fit or 0) - (starved.metrics.val_fit or 0))
        free_run_gap = abs(
            (good.metrics.val_free_run_fit or 0) - (starved.metrics.val_free_run_fit or 0)
        )
        assert free_run_gap > one_step_gap, (
            f"free-run gap {free_run_gap:.2f} should exceed one-step gap {one_step_gap:.2f}"
        )

    def test_aic_and_bic_are_reported(self) -> None:
        inputs = make_inputs(2500)
        result = fit(inputs, simulate(inputs, noise=0.03))
        assert result.metrics.aic is not None
        assert result.metrics.bic is not None
        assert result.metrics.bic > result.metrics.aic  # more parameters penalised harder

    def test_restricting_training_rows_changes_the_fit(self) -> None:
        inputs = make_inputs(3000)
        output = simulate(inputs, noise=0.03)
        full = fit(inputs, output)
        subset = fit(inputs, output, training_sample_indices=list(range(100, 900)))
        assert subset.training_rows < full.training_rows
        assert subset.coefficients != full.coefficients

    def test_rejects_too_few_training_rows(self) -> None:
        inputs = make_inputs(2000)
        with pytest.raises(ModelingDomainError) as error:
            fit(inputs, simulate(inputs, noise=0.02), training_sample_indices=[100, 101, 102])
        assert error.value.code == "INSUFFICIENT_ROWS"

    def test_ridge_runs_when_ols_would_be_rank_deficient(self) -> None:
        inputs = make_inputs(2500)
        inputs["u2"] = inputs["u1"].copy()
        output = simulate(inputs, noise=0.02)
        # Identical signals only make identical regressor columns when they also share a
        # delay; with different nk they are shifted copies and the matrix stays full rank.
        same_delay = {"u1": 3, "u2": 3}
        with pytest.raises(ModelingDomainError) as error:
            fit(inputs, output, estimator="ols", delays=same_delay)
        assert error.value.code == "DESIGN_MATRIX_RANK_DEFICIENT"

        ridge = fit(inputs, output, estimator="ridge", ridge_alpha=1e-3, delays=same_delay)
        assert ridge.metrics.val_free_run_fit is not None


class TestPriors:
    def test_correct_gain_sign_passes(self) -> None:
        inputs = make_inputs(3000)
        result = fit(inputs, simulate(inputs, noise=0.02), gain_sign={"u1": "positive"})
        assert result.prior_violations == ()

    def test_wrong_gain_sign_is_flagged(self) -> None:
        inputs = make_inputs(3000)
        result = fit(inputs, simulate(inputs, noise=0.02), gain_sign={"u1": "negative"})
        assert [v.kind for v in result.prior_violations] == ["gain_sign"]
        assert result.prior_violations[0].variable == "u1"

    def test_gain_bounds_are_checked_against_the_analytic_gain(self) -> None:
        inputs = make_inputs(3000)
        truth = sum(B["u1"]) / (1.0 + sum(AR))
        inside = fit(
            inputs,
            simulate(inputs, noise=0.02),
            gain_bounds={"u1": (truth * 0.8, truth * 1.2)},
        )
        assert inside.prior_violations == ()

        outside = fit(
            inputs,
            simulate(inputs, noise=0.02),
            gain_bounds={"u1": (truth * 5, truth * 10)},
        )
        assert [v.kind for v in outside.prior_violations] == ["gain_bounds"]

    def test_stability_is_reported(self) -> None:
        inputs = make_inputs(3000)
        result = fit(inputs, simulate(inputs, noise=0.02))
        assert result.validation.stable
        assert result.validation.max_pole_modulus < 1.0


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'modeling.db'}")
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


class TestModelingApi:
    def _version(self, client: TestClient) -> str:
        response = client.post(
            "/api/v1/simulation/generate",
            json={"scenario": "S2", "n_steps": 3000, "seed": 11, "input_count": 2},
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]["version_id"]

    def test_fit_returns_free_run_metrics_and_validation(self, client: TestClient) -> None:
        version_id = self._version(client)
        response = client.post(
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
        assert response.status_code == 200, response.text
        data = response.json()["data"]

        assert data["metrics"]["val_free_run_fit"] is not None
        assert data["validation"]["free_run_fit"] is not None
        assert data["validation"]["one_step_fit"] is not None
        assert data["validation"]["stable"] is True
        assert data["validation"]["steady_state_gains"]
        assert data["training_rows"] > 0
        assert data["free_run_series"]

    def test_violating_a_prior_blocks_the_model(self, client: TestClient) -> None:
        version_id = self._version(client)
        response = client.post(
            "/api/v1/modeling/arx/fit",
            json={
                "version_id": version_id,
                "input_columns": ["u1", "u2"],
                "output_column": "y",
                "na": 2,
                "nb": [2, 2],
                "delays": [3, 8],
                "gain_sign": {"u1": "negative"},
            },
        )
        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "PRIOR_CONSTRAINT_VIOLATED"
        assert body["error"]["details"]["violations"][0]["variable"] == "u1"

    def test_unknown_version_returns_404(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/modeling/arx/fit",
            json={
                "version_id": str(uuid4()),
                "input_columns": ["u1"],
                "output_column": "y",
                "na": 2,
                "nb": [2],
                "delays": [3],
            },
        )
        assert response.status_code == 404
