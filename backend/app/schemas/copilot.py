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
        "evaluate_model",
        "optimize_pipeline",
        "generate_report",
        "export_dataset",
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


class ProofCheckData(Schema):
    """One statically verified property of an execution plan."""

    name: str
    passed: bool
    detail: str


class ComplianceProofData(Schema):
    """Machine-checked evidence that a plan obeys the frozen safety rules.

    A plan whose proof does not pass is never executed, so this is the record of what was
    verified rather than a promise about what the agent intends to do.
    """

    proof_id: str
    passed: bool
    checks: list[ProofCheckData]
    signature: str
    code_version: str
    generated_at: str


class AgentStepRun(Schema):
    """One executed step: its inputs, its real tool output and its timing."""

    step_id: str
    tool: str
    status: Literal["pending", "waiting_confirmation", "running", "completed", "failed"]
    parameters: dict[str, Any] = Field(default_factory=dict)
    summary: str
    result: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float = 0.0
    error_code: str | None = None


class CopilotChatData(Schema):
    copilot_run_id: UUID
    plan: ExecutionPlan
    task: TaskResource | None = None
    compliance: ComplianceProofData | None = None
    step_runs: list[AgentStepRun] = Field(default_factory=list)
    conclusion: str = ""
    executed: bool = False
    # Where the plan came from. "llm" means a model authored it and it then passed the same
    # whitelist and compliance checks a rule-based plan passes; "rule_based" means the
    # deterministic planner produced it, either by configuration or after a fallback.
    plan_source: Literal["llm", "rule_based"] = "rule_based"
    llm_provider: str = "none"
    llm_model: str = "none"
    llm_fallback_reason: str | None = None


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
