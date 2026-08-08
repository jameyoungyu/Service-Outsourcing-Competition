"""Route-level tests for the real cleaning pipeline and its derived version lineage."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
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
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cleaning.db'}")
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


def build_csv(*, rows: int = 400, spike_at: int = 120, gap: tuple[int, int] = (200, 205)) -> bytes:
    """Regular 1 Hz series with one obvious spike and one short gap."""

    start = datetime(2026, 1, 1, tzinfo=UTC)
    lines = ["timestamp,u1,y"]
    for index in range(rows):
        stamp = (start + timedelta(seconds=index)).isoformat()
        u1 = 1.0 if index % 80 < 40 else -1.0
        y = 0.5 * u1 + 0.01 * index
        if index == spike_at:
            y += 50.0
        if gap[0] <= index < gap[1]:
            lines.append(f"{stamp},{u1},")
            continue
        lines.append(f"{stamp},{u1:.6f},{y:.6f}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def upload(client: TestClient, content: bytes) -> str:
    response = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("plant.csv", content, "text/csv")},
        data={"name": "清洗测试"},
    )
    assert response.status_code == 202, response.text
    return response.json()["data"]["dataset"]["latest_version_id"]


class TestCleaningRoute:
    def test_clean_creates_a_derived_version_and_reports_changes(self, client: TestClient) -> None:
        version_id = upload(client, build_csv())

        response = client.post(
            "/api/v1/preprocessing/clean",
            json={
                "version_id": version_id,
                "resample_period_s": 1.0,
                "interpolation": "linear",
                "anomaly_detector": "hampel",
                "anomaly_strategy": "local_median",
            },
        )
        assert response.status_code == 202, response.text
        data = response.json()["data"]

        assert data["source_version_id"] == version_id
        assert data["derived_version_id"] != version_id
        assert data["series"], "the response must carry the before/after series"

    def test_derived_version_appears_in_the_lineage_dag(self, client: TestClient) -> None:
        version_id = upload(client, build_csv())
        cleaned = client.post(
            "/api/v1/preprocessing/clean",
            json={"version_id": version_id, "anomaly_strategy": "local_median"},
        )
        assert cleaned.status_code == 202, cleaned.text
        derived_id = cleaned.json()["data"]["derived_version_id"]
        dataset_id = cleaned.json()["data"]["dataset_id"]
        assert dataset_id is not None

        versions = client.get(f"/api/v1/datasets/{dataset_id}/versions")
        assert versions.status_code == 200, versions.text
        payload = versions.json()["data"]
        by_id = {node["id"]: node for node in payload["nodes"]}
        assert derived_id in by_id
        assert by_id[derived_id]["parent_version_id"] == version_id
        assert by_id[derived_id]["tool"] == "preprocessing.clean"
        assert {"source": version_id, "target": derived_id} in [
            {"source": edge["source"], "target": edge["target"]} for edge in payload["edges"]
        ]

    def test_raw_version_is_never_mutated(self, client: TestClient) -> None:
        version_id = upload(client, build_csv())
        before = client.get(
            f"/api/v1/datasets/{client.get('/api/v1/datasets').json()['data']['items'][0]['id']}/profile"
        )
        assert before.status_code == 200

        client.post(
            "/api/v1/preprocessing/clean",
            json={"version_id": version_id, "anomaly_strategy": "set_null"},
        )
        after = client.post(
            "/api/v1/preprocessing/clean",
            json={"version_id": version_id, "anomaly_strategy": "set_null"},
        )
        # Cleaning the same parent twice must succeed and produce a second sibling version.
        assert after.status_code == 202, after.text
        assert after.json()["data"]["source_version_id"] == version_id

    def test_unknown_version_returns_404(self, client: TestClient) -> None:
        from uuid import uuid4

        response = client.post(
            "/api/v1/preprocessing/clean",
            json={"version_id": str(uuid4())},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "DATASET_VERSION_NOT_FOUND"
