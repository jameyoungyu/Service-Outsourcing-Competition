"""Persisted orchestration for delay estimation and collinearity analysis (phase 6)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
from algorithms.identifiability.collinearity import analyze_collinearity
from algorithms.identifiability.delay import estimate_delays
from algorithms.identifiability.regressor import IdentifiabilityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import ProcessingRun
from app.models.operation_log import OperationLog
from app.schemas.preprocessing import (
    CollinearityData,
    CollinearityRequest,
    DelayData,
    DelayPeak,
    DelayRequest,
    VariableRecommendation,
)
from app.services.contract_stubs import completed_task
from app.services.version_data import VersionDataError, VersionSeries, load_version_series


class AnalysisDomainError(Exception):
    """A client-safe delay/collinearity failure for the standard error envelope."""

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


async def run_delay_estimation(
    session: AsyncSession,
    *,
    payload: DelayRequest,
    artifact_root: Path,
) -> DelayData:
    """Prewhitened cross-correlation candidates refined on the validation split."""

    series = await _load(session, payload.version_id, artifact_root, payload.dataset_id)
    input_columns, output_column = _resolve(series, payload.input_columns, payload.output_column)

    try:
        result = estimate_delays(
            inputs={column: series.values[column] for column in input_columns},
            output=series.values[output_column],
            max_lag=payload.max_lag,
            top_k=payload.top_k,
        )
    except IdentifiabilityError as error:
        raise AnalysisDomainError(error.code, error.message, details=error.details) from error

    await _persist(
        session,
        series=series,
        run_type="preprocessing.delay",
        parameters=payload.model_dump(mode="json"),
        result=result.to_payload(),
        event="preprocessing.delay.completed",
    )

    estimates = {estimate.column: estimate for estimate in result.estimates}
    return DelayData(
        source_version_id=series.version_id,
        task=completed_task(
            stage="estimate_delays",
            message="预白化互相关候选与验证集复核已完成。",
        ),
        delays=[result.refined_delays[column] for column in input_columns],
        correlations={column: list(estimates[column].correlations) for column in input_columns},
        best_delays=dict(result.refined_delays),
        candidate_peaks={
            column: [
                DelayPeak(
                    lag=candidate.lag,
                    correlation=float(np.clip(candidate.correlation, -1.0, 1.0)),
                    confidence=candidate.confidence,
                )
                for candidate in estimates[column].candidates
            ]
            for column in input_columns
        },
        dataset_id=series.dataset_id,
        validation_fit=_finite(result.validation_fit),
        refinement_rounds=result.refinement_rounds,
        uncertain_columns=list(result.uncertain_columns),
        prewhitening_orders={
            column: estimates[column].prewhitening_order for column in input_columns
        },
    )


async def run_collinearity_analysis(
    session: AsyncSession,
    *,
    payload: CollinearityRequest,
    artifact_root: Path,
) -> CollinearityData:
    """Pearson, Spearman, VIF and condition number, with advisory recommendations."""

    series = await _load(session, payload.version_id, artifact_root, payload.dataset_id)
    input_columns, _ = _resolve(series, payload.input_columns, payload.output_column)

    try:
        result = analyze_collinearity(
            inputs={column: series.values[column] for column in input_columns},
            correlation_threshold=payload.correlation_threshold,
            vif_threshold=payload.vif_threshold,
        )
    except IdentifiabilityError as error:
        raise AnalysisDomainError(error.code, error.message, details=error.details) from error

    await _persist(
        session,
        series=series,
        run_type="preprocessing.collinearity",
        parameters=payload.model_dump(mode="json"),
        result=result.to_payload(),
        event="preprocessing.collinearity.completed",
    )

    return CollinearityData(
        source_version_id=series.version_id,
        task=completed_task(
            stage="analyze_collinearity",
            message="相关性、VIF 与条件数诊断已完成。",
        ),
        variables=list(result.variables),
        matrix=[list(row) for row in result.pearson],
        vif_scores={column: _finite(value, fallback=1e9) for column, value in result.vif.items()},
        condition_number=_finite(result.condition_number, fallback=None),
        recommendations=[
            VariableRecommendation(
                variable=item.variable,
                action=item.action,
                reason=item.reason,
                related_variables=list(item.related_variables),
            )
            for item in result.advice
        ],
        dataset_id=series.dataset_id,
        spearman_matrix=[list(row) for row in result.spearman],
        correlated_groups=[list(group) for group in result.groups],
    )


async def _load(
    session: AsyncSession,
    version_id: UUID,
    artifact_root: Path,
    dataset_id: UUID | None,
) -> VersionSeries:
    try:
        return await load_version_series(
            session,
            version_id=version_id,
            artifact_root=artifact_root,
            dataset_id=dataset_id,
        )
    except VersionDataError as error:
        raise AnalysisDomainError(
            error.code, error.message, status_code=error.status_code, details=error.details
        ) from error


def _resolve(
    series: VersionSeries,
    input_columns: list[str] | None,
    output_column: str | None,
) -> tuple[list[str], str]:
    try:
        return series.resolve_columns(input_columns=input_columns, output_column=output_column)
    except VersionDataError as error:
        raise AnalysisDomainError(
            error.code, error.message, status_code=error.status_code, details=error.details
        ) from error


async def _persist(
    session: AsyncSession,
    *,
    series: VersionSeries,
    run_type: str,
    parameters: dict[str, object],
    result: dict[str, object],
    event: str,
) -> None:
    now = datetime.now(UTC)
    run_id = uuid4()
    session.add(
        ProcessingRun(
            id=run_id,
            dataset_id=series.dataset_id if series.origin == "dataset" else None,
            source_version_id=series.version_id if series.origin == "dataset" else None,
            run_type=run_type,
            status="succeeded",
            parameters=parameters,
            result=result,
            created_at=now,
            finished_at=now,
        )
    )
    session.add(
        OperationLog(
            id=uuid4(),
            event_type=event,
            subject_id=str(series.dataset_id),
            payload_json=json.dumps(
                {
                    "run_id": str(run_id),
                    "version_id": str(series.version_id),
                    "result": result,
                    "executed_at": now.isoformat(),
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
            created_at=now,
        )
    )
    await session.commit()


def _finite(value: float, *, fallback: float | None = 0.0) -> float | None:
    return float(value) if np.isfinite(value) else fallback
