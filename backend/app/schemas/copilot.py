from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import Schema, TaskResource


class CopilotChatRequest(Schema):
    message: str = Field(min_length=1, max_length=8_000)
    dataset_id: UUID | None = None
    active_version_id: UUID | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ExecutionPlanStep(Schema):
    step_id: str
    tool: Literal[
        "profile_dataset",
        "align_and_resample",
        "detect_anomalies",
        "clean_data",
        "detect_dynamic_segments",
        "estimate_delays",
        "analyze_collinearity",
        "select_variables",
        "fit_arx",
        "optimize_pipeline",
    ]
    depends_on: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    status: Literal["pending", "waiting_confirmation", "running", "completed", "failed"] = "pending"


class ExecutionPlan(Schema):
    goal: str
    dataset_id: UUID | None = None
    steps: list[ExecutionPlanStep]
    stop_conditions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class CopilotChatData(Schema):
    copilot_run_id: UUID
    plan: ExecutionPlan
    task: TaskResource | None = None


class CopilotConfirmRequest(Schema):
    copilot_run_id: UUID
    confirmation_id: str = Field(min_length=1)
    approved: bool
    parameter_overrides: dict[str, Any] = Field(default_factory=dict)
    comment: str | None = Field(default=None, max_length=2_000)


class CopilotConfirmData(Schema):
    copilot_run_id: UUID
    confirmation_id: str
    decision: Literal["approved", "rejected"]
    task: TaskResource | None = None
