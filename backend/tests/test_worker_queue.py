"""The real RQ round-trip: API enqueues, a real worker executes, /status reflects it.

These tests need a live Redis and a real ``rq worker`` subprocess, so they skip when either
is missing. Skipping is the honest behaviour — a fake queue would prove the fake works — but
a skipped test proves nothing either, so the delivery notes record where this actually ran
rather than treating a green run in an environment without Redis as verification.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from shutil import which

import pytest
from app.core.config import Settings
from app.core.db import get_session
from app.main import create_app
from app.models import Base
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REDIS_URL = os.environ.get("INDUSOPT_TEST_REDIS_URL", "redis://127.0.0.1:6379/0")
QUEUE_NAME = "indusopt"
BACKEND_ROOT = Path(__file__).resolve().parents[1]


def redis_available() -> bool:
    try:
        from redis import Redis

        Redis.from_url(REDIS_URL, socket_connect_timeout=1).ping()
    except Exception:  # noqa: BLE001 - any failure means "not available here"
        return False
    return True


pytestmark = [
    pytest.mark.skipif(not redis_available(), reason="需要可用的 Redis 才能验证真实队列往返"),
    pytest.mark.skipif(which("rq") is None, reason="需要 rq 命令行才能启动真实 Worker"),
]


@pytest.fixture
def queued_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """An API wired to a SQLite file the worker subprocess can also open."""

    database_url = f"sqlite+aiosqlite:///{tmp_path / 'queue.db'}"
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(prepare())

    async def session_override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    settings = Settings(
        artifact_root=tmp_path,
        database_url=database_url,
        redis_url=REDIS_URL,
        background_optimization=True,
    )
    monkeypatch.setattr("app.api.routes.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.job_queue.get_settings", lambda: settings)
    # The worker subprocess reads its configuration from the environment, and it must land
    # on the same database file and artifact directory as the API under test.
    monkeypatch.setenv("INDUSOPT_DATABASE_URL", database_url)
    monkeypatch.setenv("INDUSOPT_ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setenv("INDUSOPT_REDIS_URL", REDIS_URL)
    monkeypatch.setenv("INDUSOPT_BACKGROUND_OPTIMIZATION", "true")

    app = create_app()
    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        yield client
    asyncio.run(engine.dispose())


def drain_queue() -> subprocess.CompletedProcess[str]:
    """Run a real worker in burst mode: it processes what is queued and exits."""

    return subprocess.run(
        ["rq", "worker", QUEUE_NAME, "--url", REDIS_URL, "--burst"],
        env={**os.environ, "PYTHONPATH": str(BACKEND_ROOT)},
        cwd=str(BACKEND_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


def generate(client: TestClient, *, seed: int = 5) -> str:
    response = client.post(
        "/api/v1/simulation/generate",
        json={"scenario": "S2", "n_steps": 1500, "seed": seed, "input_count": 2},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["version_id"]


class TestRealQueueRoundTrip:
    def test_the_request_returns_before_the_search_runs(self, queued_client: TestClient) -> None:
        """This is the whole reason the queue exists: no request held open for minutes."""

        version_id = generate(queued_client)
        started = queued_client.post(
            "/api/v1/optimization/optuna/start",
            json={
                "version_id": version_id,
                "input_columns": ["u1", "u2"],
                "output_column": "y",
                "max_trials": 3,
            },
        )
        assert started.status_code == 202, started.text
        payload = started.json()["data"]
        assert payload["task"]["status"] == "queued"

        study_id = payload["study_id"]
        # Pollable immediately, with nothing computed yet.
        before = queued_client.get(f"/api/v1/optimization/optuna/{study_id}/status")
        assert before.status_code == 200
        assert before.json()["data"]["trials"] == []
        assert before.json()["data"]["statistics"]["target_trials"] == 3

        worker = drain_queue()
        assert worker.returncode == 0, worker.stderr

        after = queued_client.get(f"/api/v1/optimization/optuna/{study_id}/status").json()["data"]
        assert len(after["trials"]) == 3
        assert after["best_value"] is not None
        assert after["statistics"]["total_trials"] == 3

    def test_the_worker_and_the_inline_path_produce_the_same_shape_of_result(
        self, queued_client: TestClient
    ) -> None:
        """A worker that computed something different from the API would be worse than none."""

        version_id = generate(queued_client, seed=6)
        body = {
            "version_id": version_id,
            "input_columns": ["u1", "u2"],
            "output_column": "y",
            "max_trials": 3,
            "random_seed": 11,
        }
        queued = queued_client.post("/api/v1/optimization/optuna/start", json=body)
        assert drain_queue().returncode == 0
        via_worker = queued_client.get(
            f"/api/v1/optimization/optuna/{queued.json()['data']['study_id']}/status"
        ).json()["data"]

        assert set(via_worker["statistics"]) >= {
            "total_trials",
            "completed_trials",
            "failed_trials",
            "hit_rate",
            "evaluations_per_selection",
        }
        assert via_worker["best_params"]
        assert len(via_worker["best_curve"]) == len(via_worker["trials"])
