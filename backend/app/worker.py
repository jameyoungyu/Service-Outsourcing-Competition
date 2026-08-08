"""RQ worker entry point: the long closed-loop search, run outside the request.

Start with::

    PYTHONPATH=. rq worker indusopt --url redis://localhost:6379/0

The job function is deliberately thin. It reuses the same async services the HTTP handler
uses rather than growing a second implementation that would drift — a worker that computes
something subtly different from the API is worse than no worker.

Idempotence: the job is keyed on a ``study_id`` the API allocated and already inserted as
``queued``. Re-running the same job overwrites that row rather than creating a second
study, so an RQ retry after a worker crash cannot leave two records for one request.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.schemas.optimization import OptimizationStartRequest


def run_optimization_job(study_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """RQ entry point. Synchronous by contract, async underneath.

    The worker process owns its own engine: the cached one in ``app.core.db`` belongs to
    whichever event loop created it, and sharing an asyncpg pool across processes is how
    you get connections that answer the wrong query.
    """

    return asyncio.run(_execute(UUID(study_id), payload))


async def _execute(study_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
    from app.services.optimization_service import execute_study

    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            outcome = await execute_study(
                session,
                study_id=study_id,
                payload=OptimizationStartRequest.model_validate(payload),
                artifact_root=settings.artifact_root,
            )
        return outcome
    finally:
        await engine.dispose()
