"""Tests for quality gating and quality-constrained D-optimal segment selection."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import numpy as np
import pytest
from algorithms.identifiability.gating import (
    GatingThresholds,
    estimate_noise_sigma,
    gate_windows,
    hampel_anomaly_mask,
)
from algorithms.identifiability.regressor import ArxStructure, build_regressor
from algorithms.identifiability.selection import build_window_grid
from app.core.config import Settings
from app.core.db import get_session
from app.main import create_app
from app.models import Base
from app.schemas.preprocessing import SegmentRequest
from app.services.segment_service import SegmentDomainError, run_segment_selection
from app.services.version_data import VersionSeries
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

AR = [-1.35, 0.45]
B = {"u1": [0.4, 0.15], "u2": [0.22, 0.08]}
NK = {"u1": 3, "u2": 6}


def simulate(inputs: dict[str, np.ndarray], *, noise: float, seed: int) -> np.ndarray:
    generator = np.random.default_rng(seed)
    n_samples = len(next(iter(inputs.values())))
    output = np.zeros(n_samples, dtype=float)
    history = max(len(AR), max(NK[c] + len(B[c]) - 1 for c in inputs))
    for index in range(history, n_samples):
        value = -sum(AR[lag - 1] * output[index - lag] for lag in range(1, len(AR) + 1))
        for column, signal in inputs.items():
            for lag, coefficient in enumerate(B[column]):
                value += coefficient * signal[index - NK[column] - lag]
        output[index] = value + generator.normal(0.0, noise)
    return output


def long_steady_scenario(
    *,
    n_samples: int = 4000,
    noise: float = 0.02,
    seed: int = 11,
) -> tuple[dict[str, np.ndarray], np.ndarray, list[tuple[int, int]]]:
    """Mostly flat, with four short excitation bursts at known locations."""

    generator = np.random.default_rng(seed)
    inputs = {column: np.zeros(n_samples, dtype=float) for column in B}
    bursts = [(400, 520), (1100, 1220), (1900, 2020), (2600, 2720)]
    for start, stop in bursts:
        for column in B:
            inputs[column][start:stop] = generator.uniform(-1.4, 1.4)
        inputs["u1"][start : start + (stop - start) // 2] = generator.uniform(0.9, 1.5)
    return inputs, simulate(inputs, noise=noise, seed=seed), bursts


def make_series(inputs: dict[str, np.ndarray], output: np.ndarray) -> VersionSeries:
    from uuid import uuid4

    values = {**{k: np.asarray(v, dtype=float) for k, v in inputs.items()}, "y": output}
    return VersionSeries(
        dataset_id=uuid4(),
        version_id=uuid4(),
        dataset_name="test",
        origin="simulation",
        timestamps=[],
        values=values,
        declared_inputs=tuple(inputs),
        declared_output="y",
        sample_period_seconds=1.0,
    )


def make_request(**overrides: object) -> SegmentRequest:
    from uuid import uuid4

    base: dict[str, object] = {
        "version_id": uuid4(),
        "input_columns": list(B),
        "output_column": "y",
        "window_size": 60,
        "max_segments": 6,
        "train_ratio": 0.7,
    }
    base.update(overrides)
    return SegmentRequest(**base)  # type: ignore[arg-type]


class TestNoiseAndAnomalies:
    def test_noise_sigma_recovers_the_injected_level(self) -> None:
        generator = np.random.default_rng(5)
        smooth = np.sin(np.linspace(0, 20, 4000))
        noisy = smooth + generator.normal(0.0, 0.05, 4000)
        assert estimate_noise_sigma(noisy) == pytest.approx(0.05, rel=0.15)

    def test_noise_sigma_is_zero_for_a_clean_ramp(self) -> None:
        assert estimate_noise_sigma(np.linspace(0.0, 10.0, 500)) == pytest.approx(0.0, abs=1e-9)

    def test_hampel_flags_injected_spikes(self) -> None:
        generator = np.random.default_rng(9)
        values = generator.normal(0.0, 0.1, 2000)
        spikes = [200, 700, 1500]
        values[spikes] += 15.0
        mask = hampel_anomaly_mask(values, window=11, threshold=3.0)
        assert all(mask[index] for index in spikes)
        assert mask.sum() < 80  # tolerate some false positives, not a flood

    def test_hampel_leaves_a_clean_step_alone(self) -> None:
        values = np.zeros(1000)
        values[500:] = 1.0
        mask = hampel_anomaly_mask(values, window=11, threshold=3.0)
        assert mask.sum() <= 2


class TestGating:
    def _grid_and_arrays(self) -> tuple:
        inputs, output, bursts = long_steady_scenario()
        structure = ArxStructure.create(na=2, nb=2, nk=0, input_columns=tuple(B))
        regressor = build_regressor(inputs=inputs, output=output, structure=structure)
        grid = build_window_grid(regressor, window_size=60, stride=30)
        return inputs, output, regressor, grid, bursts

    def test_steady_windows_are_rejected(self) -> None:
        inputs, output, regressor, grid, bursts = self._grid_and_arrays()
        report = gate_windows(
            window_positions=grid.positions,
            time_indices=regressor.time_indices,
            inputs=inputs,
            output=output,
        )
        assert report.accepted_count > 0
        assert report.accepted_count < grid.count
        assert "steady_state_segment" in report.rejection_counts

        for index in report.accepted_indices:
            window = report.windows[index]
            centre = (window.start_index + window.end_index) / 2
            assert any(start - 60 <= centre <= stop + 60 for start, stop in bursts), (
                f"accepted a steady window at {window.start_index}-{window.end_index}"
            )

    def test_missing_data_rejects_a_window(self) -> None:
        inputs, output, regressor, grid, _ = self._grid_and_arrays()
        output = output.copy()
        output[400:520] = np.nan
        report = gate_windows(
            window_positions=grid.positions,
            time_indices=regressor.time_indices,
            inputs=inputs,
            output=output,
            thresholds=GatingThresholds(max_missing_ratio=0.05),
        )
        assert "missing_ratio_exceeded" in report.rejection_counts

    def test_anomaly_burst_rejects_a_window(self) -> None:
        inputs, output, regressor, grid, _ = self._grid_and_arrays()
        polluted = output.copy()
        polluted[1100:1220:2] += 40.0
        report = gate_windows(
            window_positions=grid.positions,
            time_indices=regressor.time_indices,
            inputs=inputs,
            output=polluted,
            thresholds=GatingThresholds(max_anomaly_ratio=0.02),
        )
        assert "anomaly_ratio_exceeded" in report.rejection_counts

    def test_every_window_keeps_its_reasons(self) -> None:
        inputs, output, regressor, grid, _ = self._grid_and_arrays()
        report = gate_windows(
            window_positions=grid.positions,
            time_indices=regressor.time_indices,
            inputs=inputs,
            output=output,
        )
        assert len(report.windows) == grid.count
        for window in report.windows:
            assert window.accepted == (not window.rejection_reasons)

    def test_rejects_an_invalid_threshold(self) -> None:
        from algorithms.identifiability.regressor import IdentifiabilityError

        with pytest.raises(IdentifiabilityError):
            GatingThresholds(max_missing_ratio=1.5).validate()


class TestQualityConstrainedSelection:
    def test_gate_runs_before_selection_and_excludes_polluted_windows(self) -> None:
        """A spike burst is information-rich but must never survive the gate."""

        inputs, output, _ = long_steady_scenario()
        polluted = output.copy()
        polluted[1100:1220:2] += 60.0
        series = make_series(inputs, polluted)
        outcome = run_segment_selection(
            series,
            make_request(max_anomaly_ratio=0.02, max_segments=4),
        )
        for window in outcome.selection.selected:
            overlap = not (window.end_index < 1100 or window.start_index > 1220)
            assert not overlap, "selected a window inside the injected spike burst"

    def test_selection_only_uses_the_training_partition(self) -> None:
        inputs, output, _ = long_steady_scenario()
        series = make_series(inputs, output)
        outcome = run_segment_selection(series, make_request(train_ratio=0.5))
        limit = int(outcome.regressor.n_rows * 0.5)
        boundary_sample = int(outcome.regressor.time_indices[limit - 1])
        for window in outcome.selection.selected:
            assert window.end_index <= boundary_sample

    def test_information_gain_is_non_increasing(self) -> None:
        inputs, output, _ = long_steady_scenario()
        series = make_series(inputs, output)
        outcome = run_segment_selection(series, make_request())
        gains = [window.information_gain_nats for window in outcome.selection.selected]
        assert gains == sorted(gains, reverse=True)

    def test_selected_segments_land_on_the_known_bursts(self) -> None:
        inputs, output, bursts = long_steady_scenario()
        series = make_series(inputs, output)
        outcome = run_segment_selection(series, make_request(max_segments=4))
        for window in outcome.selection.selected:
            centre = (window.start_index + window.end_index) / 2
            assert any(start - 60 <= centre <= stop + 60 for start, stop in bursts)

    def test_all_windows_rejected_raises_a_domain_error(self) -> None:
        n_samples = 3000
        inputs = {column: np.zeros(n_samples) for column in B}
        output = simulate(inputs, noise=0.01, seed=3)
        series = make_series(inputs, output)
        with pytest.raises(SegmentDomainError) as error:
            run_segment_selection(series, make_request())
        assert error.value.code == "NO_DYNAMIC_SEGMENT_FOUND"

    def test_reports_lazy_speedup_and_retention(self) -> None:
        inputs, output, _ = long_steady_scenario()
        series = make_series(inputs, output)
        outcome = run_segment_selection(series, make_request(max_segments=5))
        assert outcome.selection.lazy_speedup >= 1.0
        assert outcome.selection.coverage_ratio < 1.0
        assert outcome.gating.accepted_count >= len(outcome.selection.selected)


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'segments.db'}")
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


class TestSegmentApi:
    def test_end_to_end_selection_on_a_generated_benchmark(self, api_client: TestClient) -> None:
        generated = api_client.post(
            "/api/v1/simulation/generate",
            json={"scenario": "S3", "n_steps": 3000, "seed": 42, "input_count": 3},
        )
        assert generated.status_code == 201, generated.text
        version_id = generated.json()["data"]["version_id"]

        response = api_client.post(
            "/api/v1/preprocessing/segment",
            json={
                "version_id": version_id,
                "input_columns": ["u1", "u2", "u3"],
                "output_column": "y",
                "window_size": 60,
                "max_segments": 6,
            },
        )
        assert response.status_code == 202, response.text
        data = response.json()["data"]

        assert data["selection"]["selected_count"] > 0
        assert data["selection"]["gated_count"] <= data["selection"]["candidate_count"]
        assert data["selection"]["coverage_ratio"] < 1.0
        assert data["selection"]["lazy_speedup"] >= 1.0
        assert len(data["segments"]) == data["selection"]["selected_count"]
        assert data["segments"][0]["rank"] == 1
        assert data["gated_windows"], "the gate must report every candidate it scored"

    def test_unknown_version_returns_404(self, api_client: TestClient) -> None:
        from uuid import uuid4

        response = api_client.post(
            "/api/v1/preprocessing/segment",
            json={
                "version_id": str(uuid4()),
                "input_columns": ["u1"],
                "output_column": "y",
            },
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "DATASET_VERSION_NOT_FOUND"
