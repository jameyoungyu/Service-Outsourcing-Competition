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
def dataset_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Use SQLite only for route tests; Alembic remains the production PostgreSQL path."""

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'datasets.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(prepare())

    async def session_override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(
        "app.api.routes.get_settings",
        lambda: Settings(artifact_root=tmp_path, database_url=f"sqlite+aiosqlite:///{tmp_path / 'datasets.db'}"),
    )
    app = create_app()
    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        yield client
    asyncio.run(engine.dispose())


def _upload(client: TestClient, content: bytes, name: str = "industrial.csv") -> dict[str, object]:
    response = client.post(
        "/api/v1/datasets/upload",
        files={"file": (name, content, "text/csv")},
        data={"name": "锅炉时序"},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["success"] is True
    return body["data"]


@pytest.mark.parametrize(
    ("content", "expected_code"),
    [
        (b"u1,y\n1,2\n2,3\n", "INVALID_DATASET_SCHEMA"),
        (b"timestamp,u1,y\nnot-a-time,1,2\n", "TIMESTAMP_PARSE_FAILED"),
        (b"timestamp,u1,y\n2026-01-01 00:00:00,,1\n", "INVALID_DATASET_SCHEMA"),
        (b"timestamp,u1,u1\n2026-01-01 00:00:00,1,2\n", "INVALID_DATASET_SCHEMA"),
    ],
)
def test_upload_rejects_malformed_csvs(
    dataset_client: TestClient, content: bytes, expected_code: str
) -> None:
    response = dataset_client.post(
        "/api/v1/datasets/upload",
        files={"file": ("invalid.csv", content, "text/csv")},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == expected_code


def test_upload_profile_config_lineage_and_delete(dataset_client: TestClient) -> None:
    content = b"""timestamp,u1,y,note
2026-01-01 00:00:00,0,10,normal
2026-01-01 00:00:01,0,11,normal
2026-01-01 00:00:02,,12,missing
2026-01-01 00:00:02,0,13,duplicate
2026-01-01 00:00:04,0,100,outlier
2026-01-01 00:00:05,0,15,normal
"""
    uploaded = _upload(dataset_client, content)
    dataset = uploaded["dataset"]
    assert isinstance(dataset, dict)
    dataset_id = dataset["id"]
    assert dataset["status"] == "ready"
    assert uploaded["deduplicated"] is False

    listing = dataset_client.get("/api/v1/datasets")
    assert listing.status_code == 200
    items = listing.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["row_count"] == 6
    assert items[0]["time_column"] == "timestamp"

    detail = dataset_client.get(f"/api/v1/datasets/{dataset_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["preview"]["rows"][0]["u1"] == 0

    profile = dataset_client.get(f"/api/v1/datasets/{dataset_id}/profile")
    assert profile.status_code == 200
    profile_data = profile.json()["data"]
    assert profile_data["total_rows"] == 6
    assert profile_data["total_cols"] == 4
    assert profile_data["missing_rates"]["u1"] == pytest.approx(1 / 6)
    assert profile_data["duplicate_timestamp_count"] == 1
    assert profile_data["max_consecutive_missing"]["u1"] == 1
    assert profile_data["quality_score"] < 100
    assert profile_data["column_statistics"]["y"]["q50"] is not None

    configured = dataset_client.post(
        f"/api/v1/datasets/{dataset_id}/config",
        json={
            "columns": [
                {"name": "timestamp", "role": "time"},
                {"name": "u1", "role": "input", "unit": "MW"},
                {"name": "y", "role": "output", "unit": "bar"},
                {"name": "note", "role": "ignored"},
            ]
        },
    )
    assert configured.status_code == 200, configured.text
    configured_data = configured.json()["data"]
    assert configured_data["dataset"]["input_columns"] == ["u1"]
    assert configured_data["dataset"]["output_column"] == "y"

    lineage = dataset_client.get(f"/api/v1/datasets/{dataset_id}/versions")
    assert lineage.status_code == 200
    assert len(lineage.json()["data"]["nodes"]) == 1
    assert lineage.json()["data"]["nodes"][0]["tool"] == "raw_upload"

    duplicate = _upload(dataset_client, content)
    assert duplicate["deduplicated"] is True
    assert duplicate["dataset"]["id"] == dataset_id

    deleted = dataset_client.delete(f"/api/v1/datasets/{dataset_id}")
    assert deleted.status_code == 200
    assert deleted.json()["data"]["status"] == "deleted"
    assert dataset_client.get("/api/v1/datasets").json()["data"]["page"]["total"] == 0
    assert dataset_client.get(f"/api/v1/datasets/{dataset_id}/profile").status_code == 404


def test_upload_detects_gbk_and_semicolon_delimiter(dataset_client: TestClient) -> None:
    content = "时间;u1;y\n2026-01-01 00:00:00;1;2\n2026-01-01 00:00:01;2;3\n".encode("gbk")
    uploaded = _upload(dataset_client, content, name="gbk.csv")
    dataset = uploaded["dataset"]
    assert isinstance(dataset, dict)
    assert dataset["column_count"] == 3
    detail = dataset_client.get(f"/api/v1/datasets/{dataset['id']}")
    assert detail.status_code == 200
    assert detail.json()["data"]["preview"]["columns"] == ["时间", "u1", "y"]
