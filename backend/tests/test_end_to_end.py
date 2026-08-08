"""The full A14 use case, driven through the public API exactly as a user would.

This is the acceptance test for the system as a whole. It uploads an industrial CSV, walks
the entire closed loop through the REST API, then repeats the headline scenario in a single
natural-language sentence to show the agent reaches the same place on its own.

It deliberately uses no internal function calls. If a stage regresses, this test fails in
the same way a demonstration would fail in front of a judge.
"""

from __future__ import annotations

import asyncio
import csv
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from app.core.config import Settings
from app.core.db import get_session
from app.main import create_app
from app.models import Base
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

AR = [-1.35, 0.45]
B = {"u1": [0.40, 0.14], "u2": [0.20, 0.07]}
NK = {"u1": 4, "u2": 9}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'e2e.db'}")
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


def industrial_csv(*, n_samples: int = 3000, seed: int = 31) -> bytes:
    """A plant-like record: long steady holds, a few campaigns, a spike and a short gap."""

    generator = np.random.default_rng(seed)
    inputs = {name: np.zeros(n_samples) for name in B}
    for start in (300, 900, 1500, 2100):
        for name in B:
            inputs[name][start : start + 150] = generator.uniform(-1.4, 1.4)

    output = np.zeros(n_samples)
    history = max(len(AR), max(NK[c] + len(B[c]) - 1 for c in B))
    for index in range(history, n_samples):
        value = -sum(AR[lag - 1] * output[index - lag] for lag in range(1, len(AR) + 1))
        for column, signal in inputs.items():
            for lag, coefficient in enumerate(B[column]):
                value += coefficient * signal[index - NK[column] - lag]
        output[index] = value + generator.normal(0.0, 0.02)

    output[1234] += 25.0  # an obvious sensor spike
    start_time = datetime(2026, 3, 1, tzinfo=UTC)
    lines = ["timestamp,u1,u2,y"]
    for index in range(n_samples):
        stamp = (start_time + timedelta(seconds=index)).isoformat()
        y = "" if 2000 <= index < 2004 else f"{output[index]:.6f}"  # a short gap
        lines.append(f"{stamp},{inputs['u1'][index]:.6f},{inputs['u2'][index]:.6f},{y}")
    return ("\n".join(lines) + "\n").encode("utf-8")


class TestFullClosedLoop:
    def test_industrial_csv_through_the_entire_pipeline(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        # 1. Upload
        upload = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("tower.csv", industrial_csv(), "text/csv")},
            data={"name": "1号塔"},
        )
        assert upload.status_code == 202, upload.text
        dataset = upload.json()["data"]["dataset"]
        dataset_id, raw_version = dataset["id"], dataset["latest_version_id"]

        # 2. Confirm column roles
        config = client.post(
            f"/api/v1/datasets/{dataset_id}/config",
            json={
                "time_column": "timestamp",
                "input_columns": ["u1", "u2"],
                "output_column": "y",
            },
        )
        assert config.status_code == 200, config.text

        # 3. Quality profile
        profile = client.get(f"/api/v1/datasets/{dataset_id}/profile")
        assert profile.status_code == 200, profile.text
        assert profile.json()["data"]["quality_score"] >= 0

        # 4. Clean and regularise -> a new immutable version
        cleaned = client.post(
            "/api/v1/preprocessing/clean",
            json={
                "version_id": raw_version,
                "resample_period_s": 1.0,
                "interpolation": "linear",
                "anomaly_detector": "hampel",
                "anomaly_strategy": "local_median",
            },
        )
        assert cleaned.status_code == 202, cleaned.text
        clean_version = cleaned.json()["data"]["derived_version_id"]
        assert clean_version != raw_version

        # Lineage records the derivation.
        versions = client.get(f"/api/v1/datasets/{dataset_id}/versions").json()["data"]
        by_id = {node["id"]: node for node in versions["nodes"]}
        assert by_id[clean_version]["parent_version_id"] == raw_version

        # 5. Gate + D-optimal selection
        segment = client.post(
            "/api/v1/preprocessing/segment",
            json={
                "version_id": clean_version,
                "dataset_id": dataset_id,
                "input_columns": ["u1", "u2"],
                "output_column": "y",
                "window_size": 60,
                "max_segments": 6,
            },
        )
        assert segment.status_code == 202, segment.text
        selection = segment.json()["data"]["selection"]
        assert selection["selected_count"] > 0
        assert selection["gated_count"] <= selection["candidate_count"]
        assert selection["coverage_ratio"] < 1.0

        # 6. Delay estimation
        delay = client.post(
            "/api/v1/preprocessing/delay",
            json={
                "version_id": clean_version,
                "dataset_id": dataset_id,
                "input_columns": ["u1", "u2"],
                "output_column": "y",
                "max_lag": 25,
            },
        )
        assert delay.status_code == 202, delay.text
        delays = delay.json()["data"]["best_delays"]
        assert abs(delays["u1"] - NK["u1"]) <= 3, delays
        assert abs(delays["u2"] - NK["u2"]) <= 3, delays

        # 7. Collinearity
        collinearity = client.post(
            "/api/v1/preprocessing/collinearity",
            json={
                "version_id": clean_version,
                "dataset_id": dataset_id,
                "input_columns": ["u1", "u2"],
            },
        )
        assert collinearity.status_code == 202, collinearity.text
        assert collinearity.json()["data"]["condition_number"] is not None

        # 8. Identification, evaluated both ways
        fitted = client.post(
            "/api/v1/modeling/arx/fit",
            json={
                "version_id": clean_version,
                "dataset_id": dataset_id,
                "input_columns": ["u1", "u2"],
                "output_column": "y",
                "na": 2,
                "nb": [2, 2],
                "delays": [delays["u1"], delays["u2"]],
                "gain_sign": {"u1": "positive"},
            },
        )
        assert fitted.status_code == 200, fitted.text
        model = fitted.json()["data"]
        assert model["validation"]["free_run_fit"] > 60.0
        assert model["validation"]["stable"] is True
        assert model["metrics"]["val_fit"] is not None

        # 9. Closed-loop optimisation
        study = client.post(
            "/api/v1/optimization/optuna/start",
            json={
                "version_id": clean_version,
                "input_columns": ["u1", "u2"],
                "output_column": "y",
                "max_trials": 8,
                "random_seed": 21,
            },
        )
        assert study.status_code == 202, study.text
        study_id = study.json()["data"]["study_id"]
        status = client.get(f"/api/v1/optimization/optuna/{study_id}/status").json()["data"]
        assert status["best_value"] is not None
        assert status["statistics"]["evaluations_per_selection"] > 1.0

        # 10. Provenance-bound report
        report = client.post(
            "/api/v1/reports/generate",
            json={"dataset_id": dataset_id, "study_id": study_id},
        )
        assert report.status_code == 200, report.text
        report_data = report.json()["data"]
        assert report_data["fully_resolved"] is True
        assert report_data["bindings"]
        assert "{{" not in report_data["markdown"]
        assert (tmp_path / report_data["artifact_uri"]).is_file()

        # 11. Export the optimised dataset
        export = client.post(
            "/api/v1/delivery/export",
            json={
                "version_id": clean_version,
                "dataset_id": dataset_id,
                "input_columns": ["u1", "u2"],
                "output_column": "y",
            },
        )
        assert export.status_code == 200, export.text
        delivery = export.json()["data"]
        assert 0 < delivery["exported_rows"] < delivery["source_rows"]

        exported = tmp_path / delivery["csv_uri"]
        with exported.open(encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        assert len(rows) - 1 == delivery["exported_rows"]
        assert rows[0] == delivery["columns"]

    def test_one_sentence_drives_the_same_pipeline(self, client: TestClient) -> None:
        """The brief's headline claim: natural language in, finished analysis out."""

        upload = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("tower.csv", industrial_csv(seed=44), "text/csv")},
            data={"name": "2号塔"},
        )
        dataset = upload.json()["data"]["dataset"]
        dataset_id, version_id = dataset["id"], dataset["latest_version_id"]
        client.post(
            f"/api/v1/datasets/{dataset_id}/config",
            json={
                "time_column": "timestamp",
                "input_columns": ["u1", "u2"],
                "output_column": "y",
            },
        )

        chat = client.post(
            "/api/v1/copilot/chat",
            json={
                "message": "提取 2 号塔高信噪比的动态数据，估计时滞并处理共线性，然后做 ARX 辨识",
                "dataset_id": dataset_id,
                "active_version_id": version_id,
            },
        )
        assert chat.status_code == 200, chat.text
        data = chat.json()["data"]

        assert data["compliance"]["passed"] is True
        assert data["executed"] is True
        runs = {run["tool"]: run for run in data["step_runs"]}
        for tool in ("detect_dynamic_segments", "estimate_delays", "fit_arx"):
            assert runs[tool]["status"] == "completed", (tool, runs[tool])

        # The agent reports the tools' numbers, not its own.
        assert runs["fit_arx"]["result"]["val_free_run_fit"] is not None
        assert runs["estimate_delays"]["result"]["delays"]

        # And the whole run is citable by the report layer.
        report = client.post("/api/v1/reports/generate", json={"dataset_id": dataset_id})
        assert report.status_code == 200, report.text
        assert report.json()["data"]["fully_resolved"] is True
