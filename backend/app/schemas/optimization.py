from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import Schema, TaskResource


class OptimizationStartRequest(Schema):
    version_id: UUID
    input_columns: list[str] = Field(min_length=1)
    output_column: str = Field(min_length=1)
    max_trials: int = Field(default=50, ge=1, le=10_000)
    timeout_seconds: int | None = Field(default=None, ge=1, le=86_400)
    search_space: dict[str, Any] = Field(default_factory=dict)
    random_seed: int = Field(default=42, ge=0, le=2_147_483_647)


class OptimizationStartData(Schema):
    study_id: UUID
    task: TaskResource


class OptimizationTrial(Schema):
    trial_id: int = Field(ge=0)
    state: Literal["queued", "running", "complete", "pruned", "failed"]
    value: float | None = None
    params: dict[str, Any]
    created_at: datetime
    finished_at: datetime | None = None
    error_code: str | None = None


class OptimizationStatusData(Schema):
    study_id: UUID
    task: TaskResource
    trials: list[OptimizationTrial]
    best_trial_id: int | None = None
    best_value: float | None = None
    best_curve: list[float | None]
    param_importances: dict[str, float]
    # Cache-hit rate, trial counts and timings — the phase-8 acceptance evidence.
    statistics: dict[str, Any] = Field(default_factory=dict)
    best_params: dict[str, Any] = Field(default_factory=dict)
    # Set when this study reused parameters learned from a different dataset.
    warm_started_from: UUID | None = None
