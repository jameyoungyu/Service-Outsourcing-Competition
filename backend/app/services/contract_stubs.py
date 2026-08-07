"""Shared task and placeholder resources used by staged application services."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.schemas.common import TaskProgress, TaskResource, TaskState
from app.schemas.datasets import DatasetSource, DatasetState, DatasetSummary


def now() -> datetime:
    return datetime.now(UTC)


def queued_task(*, status: TaskState = "queued", stage: str = "queued") -> TaskResource:
    created_at = now()
    return TaskResource(
        id=uuid4(),
        status=status,
        progress=TaskProgress(
            current=0,
            total=1,
            percent=0,
            stage=stage,
            message="阶段 1 契约骨架：任务尚未接入实际算法。",
        ),
        created_at=created_at,
    )


def completed_task(*, stage: str, message: str) -> TaskResource:
    completed_at = now()
    return TaskResource(
        id=uuid4(),
        status="succeeded",
        progress=TaskProgress(
            current=1,
            total=1,
            percent=100,
            stage=stage,
            message=message,
        ),
        created_at=completed_at,
        started_at=completed_at,
        finished_at=completed_at,
    )


def dataset_summary(
    dataset_id: UUID,
    *,
    name: str = "Phase 1 contract dataset",
    source: DatasetSource = "simulation",
    status: DatasetState = "ready",
    version_id: UUID | None = None,
) -> DatasetSummary:
    timestamp = now()
    return DatasetSummary(
        id=dataset_id,
        name=name,
        source=source,
        status=status,
        row_count=0,
        column_count=0,
        latest_version_id=version_id,
        created_at=timestamp,
        updated_at=timestamp,
    )


def new_id() -> UUID:
    return uuid4()
