"""Agent orchestration: plan, verify, execute real tools, decide (phase 9).

Four layers, matching the phase plan:

* **Planner** turns the request into a whitelisted step list (``algorithms.agent.planner``).
* **Validator** statically verifies it and emits a compliance proof
  (``algorithms.agent.compliance``). A plan that fails does not run.
* **Executor** dispatches each step to the same services the REST API uses. It never
  evaluates model-authored code and never computes a metric itself — every number in a run
  record comes from an algorithm module.
* **Controller** decides after each step whether to continue, stop, or wait for a human.

The agent's own output is a plan and an explanation. All arithmetic belongs to the tools,
which is what makes the audit trail meaningful.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from algorithms.agent.compliance import ComplianceProof, verify_plan
from algorithms.agent.planner import (
    PlannedStep,
    RuleBasedPlanner,
    parse_intent,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import ProcessingRun
from app.models.operation_log import OperationLog
from app.schemas.copilot import (
    AgentStepRun,
    ComplianceProofData,
    CopilotChatData,
    CopilotChatRequest,
    ExecutionPlan,
    ExecutionPlanStep,
)
from app.schemas.modeling import ArxFitRequest
from app.schemas.optimization import OptimizationStartRequest
from app.schemas.preprocessing import SegmentRequest
from app.services.contract_stubs import completed_task
from app.services.modeling_service import ModelingDomainError, fit_arx_core
from app.services.optimization_service import run_study
from app.services.preprocessing_analysis_service import AnalysisDomainError
from app.services.segment_service import SegmentDomainError, run_segment_selection
from app.services.version_data import VersionDataError, VersionSeries, load_version_series

CODE_VERSION = "1.1.0-agent"


class AgentDomainError(Exception):
    """A client-safe agent failure for the standard error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


@dataclass
class StepExecution:
    """The record of one executed step, kept whether it succeeded or not."""

    step_id: str
    tool: str
    status: str
    parameters: dict[str, Any]
    summary: str
    result: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    error_code: str | None = None


async def run_copilot(
    session: AsyncSession,
    *,
    payload: CopilotChatRequest,
    artifact_root: Path,
) -> CopilotChatData:
    """Parse, plan, verify and (when the proof passes) execute."""

    intent = parse_intent(payload.message)
    steps, assumptions, stop_conditions = RuleBasedPlanner().plan(intent)

    confirmed = frozenset(
        str(step_id) for step_id in payload.context.get("confirmed_steps", []) or []
    )
    raw_steps = [
        {
            "step_id": step.step_id,
            "tool": step.tool,
            "depends_on": list(step.depends_on),
            "parameters": dict(step.parameters),
            "requires_confirmation": step.requires_confirmation,
        }
        for step in steps
    ]
    proof = verify_plan(raw_steps, code_version=CODE_VERSION, confirmed_steps=confirmed)

    run_id = uuid4()
    executions: list[StepExecution] = []
    series: VersionSeries | None = None

    if proof.passed and payload.active_version_id is not None:
        try:
            series = await load_version_series(
                session,
                version_id=payload.active_version_id,
                artifact_root=artifact_root,
                dataset_id=payload.dataset_id,
            )
        except VersionDataError as error:
            raise AgentDomainError(
                error.code, error.message, status_code=error.status_code, details=error.details
            ) from error
        executions = _execute(series, steps, intent.parameters)

    conclusion = _conclusion(proof, executions, intent.goals)
    await _persist(
        session,
        run_id=run_id,
        payload=payload,
        proof=proof,
        executions=executions,
        series=series,
    )

    return CopilotChatData(
        copilot_run_id=run_id,
        plan=ExecutionPlan(
            goal=payload.message,
            dataset_id=payload.dataset_id,
            steps=[
                ExecutionPlanStep(
                    step_id=step.step_id,
                    tool=step.tool,
                    depends_on=list(step.depends_on),
                    parameters=dict(step.parameters),
                    requires_confirmation=step.requires_confirmation,
                    status=_status_of(step.step_id, executions),
                )
                for step in steps
            ],
            stop_conditions=stop_conditions,
            assumptions=assumptions,
        ),
        task=completed_task(stage="copilot_plan", message=conclusion),
        compliance=ComplianceProofData(**proof.to_payload()),
        step_runs=[
            AgentStepRun(
                step_id=execution.step_id,
                tool=execution.tool,
                status=execution.status,
                parameters=execution.parameters,
                summary=execution.summary,
                result=execution.result,
                duration_ms=execution.duration_ms,
                error_code=execution.error_code,
            )
            for execution in executions
        ],
        conclusion=conclusion,
        executed=bool(executions),
    )


def _execute(
    series: VersionSeries,
    steps: list[PlannedStep],
    hints: dict[str, Any],
) -> list[StepExecution]:
    """Run each step against the real services, stopping at the first hard failure."""

    try:
        input_columns, output_column = series.resolve_columns(
            input_columns=None, output_column=None
        )
    except VersionDataError as error:
        return [
            StepExecution(
                step_id="s0",
                tool="profile_dataset",
                status="failed",
                parameters={},
                summary=error.message,
                error_code=error.code,
            )
        ]

    context: dict[str, Any] = {
        "input_columns": input_columns,
        "output_column": output_column,
        "selected_indices": [],
        "delays": {column: 0 for column in input_columns},
        "na": 2,
        "nb": 2,
    }
    executions: list[StepExecution] = []

    for step in steps:
        if step.requires_confirmation:
            executions.append(
                StepExecution(
                    step_id=step.step_id,
                    tool=step.tool,
                    status="waiting_confirmation",
                    parameters=dict(step.parameters),
                    summary="高影响操作，等待人工确认后执行。",
                )
            )
            continue

        started = time.perf_counter()
        try:
            summary, result = _dispatch(step, series, context, hints)
            status = "completed"
            error_code = None
        except (SegmentDomainError, ModelingDomainError, AnalysisDomainError) as error:
            summary, result, status, error_code = error.message, {}, "failed", error.code
        except VersionDataError as error:
            summary, result, status, error_code = error.message, {}, "failed", error.code

        executions.append(
            StepExecution(
                step_id=step.step_id,
                tool=step.tool,
                status=status,
                parameters=dict(step.parameters),
                summary=summary,
                result=result,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                error_code=error_code,
            )
        )
        if status == "failed":
            break
    return executions


def _dispatch(
    step: PlannedStep,
    series: VersionSeries,
    context: dict[str, Any],
    hints: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Map one whitelisted tool to the service that implements it."""

    inputs = {column: series.values[column] for column in context["input_columns"]}
    output = series.values[context["output_column"]]

    if step.tool == "profile_dataset":
        from algorithms.pipeline.fingerprint import build_fingerprint

        fingerprint = build_fingerprint(inputs=inputs, output=output)
        return (
            f"数据画像完成：{series.n_samples} 个样本，"
            f"{len(context['input_columns'])} 个输入变量。",
            {"fingerprint": fingerprint.to_payload(), "n_samples": series.n_samples},
        )

    if step.tool in {"detect_anomalies", "clean_data", "align_and_resample"}:
        from algorithms.identifiability.gating import estimate_noise_sigma, hampel_anomaly_mask

        mask = hampel_anomaly_mask(output)
        ratio = float(mask.mean()) if mask.size else 0.0
        return (
            f"检出疑似异常点 {int(mask.sum())} 个（占比 {ratio:.2%}），"
            f"噪声水平估计 {estimate_noise_sigma(output):.4g}。",
            {"anomaly_count": int(mask.sum()), "anomaly_ratio": ratio},
        )

    if step.tool == "detect_dynamic_segments":
        segment_request = SegmentRequest(
            version_id=series.version_id,
            input_columns=context["input_columns"],
            output_column=context["output_column"],
            window_size=int(step.parameters.get("window_size", hints.get("window_size", 60))),
            max_segments=int(step.parameters.get("max_segments", hints.get("max_segments", 8))),
        )
        outcome = run_segment_selection(series, segment_request)
        context["selected_indices"] = outcome.selected_sample_indices
        return (
            f"质量门控通过 {outcome.gating.accepted_count}/{len(outcome.gating.windows)} 个窗口，"
            f"D-最优优选出 {len(outcome.selection.selected)} 个区间，"
            f"采样占比 {outcome.selection.coverage_ratio:.2%}。",
            {
                "selected_count": len(outcome.selection.selected),
                "coverage_ratio": outcome.selection.coverage_ratio,
                "gated_count": outcome.gating.accepted_count,
                "candidate_count": len(outcome.gating.windows),
            },
        )

    if step.tool == "estimate_delays":
        from algorithms.identifiability.delay import estimate_delays

        delay_result = estimate_delays(
            inputs=inputs,
            output=output,
            max_lag=int(step.parameters.get("max_lag", hints.get("max_lag", 30))),
        )
        context["delays"] = dict(delay_result.refined_delays)
        rendered = ", ".join(f"{k}={v}" for k, v in delay_result.refined_delays.items())
        return (
            f"预白化互相关与验证集复核给出时滞：{rendered}；"
            f"验证集自由仿真 FIT {delay_result.validation_fit:.2f}%。",
            {
                "delays": dict(delay_result.refined_delays),
                "validation_fit": delay_result.validation_fit,
            },
        )

    if step.tool in {"analyze_collinearity", "select_variables"}:
        from algorithms.identifiability.collinearity import analyze_collinearity

        if len(inputs) < 2:
            return "输入变量少于两个，跳过共线性分析。", {"skipped": True}
        collinearity = analyze_collinearity(inputs=inputs)
        drops = [item.variable for item in collinearity.advice if item.action == "drop"]
        return (
            f"条件数 {collinearity.condition_number:.1f}，"
            f"检出 {len(collinearity.groups)} 个高相关变量组"
            + (f"，建议剔除 {', '.join(drops)}（需人工确认）。" if drops else "。"),
            {
                "condition_number": collinearity.condition_number,
                "groups": [list(group) for group in collinearity.groups],
                "suggested_drops": drops,
            },
        )

    if step.tool in {"fit_arx", "evaluate_model"}:
        fit_request = ArxFitRequest(
            version_id=series.version_id,
            input_columns=context["input_columns"],
            output_column=context["output_column"],
            na=int(context["na"]),
            nb={column: int(context["nb"]) for column in context["input_columns"]},
            delays={column: int(context["delays"][column]) for column in context["input_columns"]},
            training_sample_indices=list(context["selected_indices"]),
        )
        fit_result = fit_arx_core(
            inputs=inputs,
            output=output,
            payload=fit_request,
            input_columns=context["input_columns"],
        )
        free_run = fit_result.metrics.val_free_run_fit or float("nan")
        one_step = fit_result.metrics.val_fit or float("nan")
        return (
            f"ARX 辨识完成：验证集自由仿真 FIT {free_run:.2f}%"
            f"（一步预测 {one_step:.2f}%，差值 {fit_result.validation.fit_gap:.2f}），"
            f"模型{'稳定' if fit_result.validation.stable else '不稳定'}。",
            {
                "val_free_run_fit": free_run,
                "val_one_step_fit": one_step,
                "fit_gap": fit_result.validation.fit_gap,
                "stable": fit_result.validation.stable,
                "training_rows": fit_result.training_rows,
            },
        )

    if step.tool == "optimize_pipeline":
        study_request = OptimizationStartRequest(
            version_id=series.version_id,
            input_columns=context["input_columns"],
            output_column=context["output_column"],
            max_trials=int(step.parameters.get("max_trials", hints.get("max_trials", 15))),
        )
        study = run_study(
            series,
            study_request,
            input_columns=context["input_columns"],
            output_column=context["output_column"],
        )
        return (
            f"闭环寻优完成：{study.statistics['completed_trials']} 个有效试验，"
            f"最优目标值 {study.best_value:.4f}，"
            f"验证集自由仿真 FIT {study.best_metrics.get('val_free_run_fit', float('nan')):.2f}%。",
            {
                "best_value": study.best_value,
                "best_params": study.best_params,
                "statistics": study.statistics,
            },
        )

    if step.tool == "generate_report":
        return "报告生成已排入交付阶段，所有数值均从运行记录解析。", {"deferred": True}

    if step.tool == "export_dataset":
        return "数据集导出为高影响操作，需人工确认后执行。", {"deferred": True}

    return f"工具 {step.tool} 暂无执行实现。", {"skipped": True}


def _status_of(step_id: str, executions: list[StepExecution]) -> str:
    for execution in executions:
        if execution.step_id == step_id:
            return execution.status
    return "pending"


def _conclusion(
    proof: ComplianceProof,
    executions: list[StepExecution],
    goals: frozenset[str],
) -> str:
    if not proof.passed:
        reasons = "；".join(check.detail for check in proof.failures)
        return f"计划未通过合规校验，已阻止执行：{reasons}"
    if not executions:
        return "计划已生成并通过合规校验；请指定数据版本后执行。"
    failed = [execution for execution in executions if execution.status == "failed"]
    waiting = [execution for execution in executions if execution.status == "waiting_confirmation"]
    completed = [execution for execution in executions if execution.status == "completed"]
    parts = [f"已执行 {len(completed)} 个步骤"]
    if waiting:
        parts.append(f"{len(waiting)} 个高影响步骤等待人工确认")
    if failed:
        parts.append(f"{len(failed)} 个步骤失败（{failed[0].error_code}）")
    parts.append(f"识别到的意图：{', '.join(sorted(goals)) or '仅数据诊断'}")
    return "；".join(parts) + "。"


async def _persist(
    session: AsyncSession,
    *,
    run_id: UUID,
    payload: CopilotChatRequest,
    proof: ComplianceProof,
    executions: list[StepExecution],
    series: VersionSeries | None,
) -> None:
    """Persist the full audit trail: request, proof, every step's input and output."""

    now = datetime.now(UTC)
    session.add(
        ProcessingRun(
            id=run_id,
            dataset_id=series.dataset_id if series and series.origin == "dataset" else None,
            source_version_id=series.version_id if series and series.origin == "dataset" else None,
            run_type="agent.copilot",
            status="succeeded" if proof.passed else "rejected",
            parameters=payload.model_dump(mode="json"),
            result={
                "compliance": proof.to_payload(),
                "steps": [
                    {
                        "step_id": execution.step_id,
                        "tool": execution.tool,
                        "status": execution.status,
                        "parameters": execution.parameters,
                        "summary": execution.summary,
                        "result": execution.result,
                        "duration_ms": execution.duration_ms,
                        "error_code": execution.error_code,
                    }
                    for execution in executions
                ],
            },
            created_at=now,
            finished_at=now,
        )
    )
    session.add(
        OperationLog(
            id=uuid4(),
            event_type="agent.copilot.completed",
            subject_id=str(payload.dataset_id) if payload.dataset_id else str(run_id),
            payload_json=json.dumps(
                {
                    "copilot_run_id": str(run_id),
                    "message": payload.message,
                    "compliance_passed": proof.passed,
                    "proof_id": proof.proof_id,
                    "executed_steps": len(executions),
                    "executed_at": now.isoformat(),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            created_at=now,
        )
    )
    await session.commit()
