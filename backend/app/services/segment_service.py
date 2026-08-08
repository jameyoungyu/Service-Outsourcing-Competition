"""Quality-constrained D-optimal dynamic segment selection.

Two stages, in this order:

1. **Quality gate** (``algorithms.identifiability.gating``) rejects windows with too much
   missing data, too many anomalies, too little excitation or too poor an SNR.
2. **D-optimal selection** (``algorithms.identifiability.selection``) greedily maximises
   ``log det`` of the Fisher information over the survivors, accelerated with CELF.

The gate runs first on purpose: a spike burst scores highly on ``log det`` precisely
because it is wild, so letting the information criterion see unvetted data would select
exactly the samples an engineer would throw away.

Selection only ever looks at the training partition, so the validation and test tails stay
untouched for the later evaluation stages.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
from algorithms.identifiability.gating import GatingReport, GatingThresholds, gate_windows
from algorithms.identifiability.regressor import (
    ArxStructure,
    IdentifiabilityError,
    RegressorMatrix,
    build_regressor,
)
from algorithms.identifiability.selection import (
    SelectionResult,
    build_window_grid,
    select_informative_windows,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import ProcessingRun
from app.models.operation_log import OperationLog
from app.schemas.preprocessing import (
    DynamicSegment,
    GatedWindow,
    SegmentData,
    SegmentRequest,
    SelectionSummary,
)
from app.services.contract_stubs import completed_task
from app.services.version_data import VersionDataError, VersionSeries, load_version_series

MAX_RESPONSE_POINTS = 4_000


class SegmentDomainError(Exception):
    """A client-safe segment-selection failure for the standard error envelope."""

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


@dataclass(frozen=True)
class SegmentSelectionOutcome:
    """Everything the API, the optimiser and the report need from one selection run."""

    series: VersionSeries
    regressor: RegressorMatrix
    structure: ArxStructure
    gating: GatingReport
    selection: SelectionResult
    input_columns: list[str]
    output_column: str
    train_rows: int
    selected_sample_indices: list[int]


def run_segment_selection(
    series: VersionSeries,
    payload: SegmentRequest,
) -> SegmentSelectionOutcome:
    """Pure computation: gate then select. No database, no artifacts, easy to test."""

    input_columns, output_column = series.resolve_columns(
        input_columns=payload.input_columns,
        output_column=payload.output_column,
    )
    structure = ArxStructure.create(
        na=payload.na,
        nb=payload.nb,
        nk=payload.nk,
        input_columns=input_columns,
    )
    inputs = {column: series.values[column] for column in input_columns}
    output = series.values[output_column]

    try:
        regressor = build_regressor(inputs=inputs, output=output, structure=structure)
    except IdentifiabilityError as error:
        raise SegmentDomainError(error.code, error.message, details=error.details) from error

    train_rows = int(regressor.n_rows * payload.train_ratio)
    if train_rows < payload.window_size:
        raise SegmentDomainError(
            "INSUFFICIENT_ROWS",
            "训练区间长度不足以切出一个候选窗口。",
            details={"train_rows": train_rows, "window_size": payload.window_size},
        )

    stride = payload.stride or max(1, payload.window_size // 2)
    try:
        grid = build_window_grid(
            regressor,
            window_size=payload.window_size,
            stride=stride,
            row_range=(0, train_rows),
        )
    except IdentifiabilityError as error:
        raise SegmentDomainError(error.code, error.message, details=error.details) from error

    gating = gate_windows(
        window_positions=grid.positions,
        time_indices=regressor.time_indices,
        inputs=inputs,
        output=output,
        thresholds=GatingThresholds(
            max_missing_ratio=payload.max_missing_ratio,
            max_anomaly_ratio=payload.max_anomaly_ratio,
            min_snr_db=payload.min_snr_db,
            min_input_activity_ratio=payload.min_input_activity_ratio,
        ),
    )
    if not gating.accepted_indices:
        raise SegmentDomainError(
            "NO_DYNAMIC_SEGMENT_FOUND",
            "所有候选窗口都未通过质量门控，请放宽阈值或补充激励试验。",
            details={
                "candidate_count": grid.count,
                "rejection_counts": gating.rejection_counts,
            },
        )

    gated_grid = grid.subset(list(gating.accepted_indices))
    try:
        selection = select_informative_windows(
            regressor,
            gated_grid,
            budget_windows=payload.max_segments,
            ridge=payload.ridge,
            min_information_gain_bits=payload.min_information_gain_bits,
            inputs=inputs,
        )
    except IdentifiabilityError as error:
        raise SegmentDomainError(error.code, error.message, details=error.details) from error

    selected_samples = sorted(
        int(value) for value in regressor.time_indices[selection.row_positions]
    )
    return SegmentSelectionOutcome(
        series=series,
        regressor=regressor,
        structure=structure,
        gating=gating,
        selection=selection,
        input_columns=input_columns,
        output_column=output_column,
        train_rows=train_rows,
        selected_sample_indices=selected_samples,
    )


async def select_dynamic_segments(
    session: AsyncSession,
    *,
    payload: SegmentRequest,
    artifact_root: Path,
) -> SegmentData:
    """Load the version, run the two-stage selection and persist an auditable run."""

    try:
        series = await load_version_series(
            session,
            version_id=payload.version_id,
            artifact_root=artifact_root,
            dataset_id=payload.dataset_id,
        )
    except VersionDataError as error:
        raise SegmentDomainError(
            error.code, error.message, status_code=error.status_code, details=error.details
        ) from error

    outcome = run_segment_selection(series, payload)
    now = datetime.now(UTC)
    run_id = uuid4()
    summary = _selection_summary(outcome)
    session.add(
        ProcessingRun(
            id=run_id,
            dataset_id=series.dataset_id if series.origin == "dataset" else None,
            source_version_id=series.version_id if series.origin == "dataset" else None,
            run_type="preprocessing.segment",
            status="succeeded",
            parameters=payload.model_dump(mode="json"),
            result={
                "selection": summary.model_dump(mode="json"),
                "selected_sample_indices": outcome.selected_sample_indices[:MAX_RESPONSE_POINTS],
                "origin": series.origin,
            },
            created_at=now,
            finished_at=now,
        )
    )
    session.add(
        OperationLog(
            id=uuid4(),
            event_type="preprocessing.segment.completed",
            subject_id=str(series.dataset_id),
            payload_json=json.dumps(
                {
                    "run_id": str(run_id),
                    "version_id": str(series.version_id),
                    "selected_windows": [
                        window.to_payload() for window in outcome.selection.selected
                    ],
                    "rejection_counts": outcome.gating.rejection_counts,
                    "executed_at": now.isoformat(),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            created_at=now,
        )
    )
    await session.commit()

    return SegmentData(
        source_version_id=series.version_id,
        dataset_id=series.dataset_id,
        task=completed_task(
            stage="detect_dynamic_segments",
            message="质量门控与 D-最优信息增益优选已完成。",
        ),
        timestamps=list(series.timestamps[:MAX_RESPONSE_POINTS]),
        series=_series_projection(outcome),
        segments=_segments(outcome),
        selection=summary,
        gated_windows=[GatedWindow(**window.to_payload()) for window in outcome.gating.windows],
        selected_indices=outcome.selected_sample_indices[:MAX_RESPONSE_POINTS],
    )


def _selection_summary(outcome: SegmentSelectionOutcome) -> SelectionSummary:
    selection = outcome.selection
    excitation = selection.excitation
    retention = selection.information_retention
    return SelectionSummary(
        candidate_count=len(outcome.gating.windows),
        gated_count=outcome.gating.accepted_count,
        selected_count=len(selection.selected),
        selected_rows=int(selection.row_positions.size),
        coverage_ratio=selection.coverage_ratio,
        baseline_log_det=_finite(selection.baseline_log_det),
        selected_log_det=_finite(selection.selected_log_det),
        information_retention=None if not np.isfinite(retention) else float(retention),
        evaluated_candidates=selection.evaluated_candidates,
        naive_candidate_evaluations=selection.naive_candidate_evaluations,
        lazy_speedup=selection.lazy_speedup,
        stopped_reason=selection.stopped_reason,
        budget_advisory=selection.budget_advisory,
        condition_number=(
            None if not np.isfinite(excitation.condition_number) else excitation.condition_number
        ),
        excitation_satisfied=excitation.excitation_satisfied,
        persistent_excitation_order=dict(excitation.persistent_excitation_order),
        required_excitation_order=dict(excitation.required_excitation_order),
        rejection_counts=dict(outcome.gating.rejection_counts),
        noise_sigma=outcome.gating.noise_sigma,
    )


def _segments(outcome: SegmentSelectionOutcome) -> list[DynamicSegment]:
    quality_by_index = {window.window_index: window for window in outcome.gating.windows}
    timestamps = outcome.series.timestamps
    segments: list[DynamicSegment] = []
    for window in outcome.selection.selected:
        quality = quality_by_index.get(window.window_index)
        segments.append(
            DynamicSegment(
                segment_id=f"seg_{window.rank:02d}",
                start_index=window.start_index,
                end_index=window.end_index,
                start_time=_timestamp_at(timestamps, window.start_index),
                end_time=_timestamp_at(timestamps, window.end_index),
                snr_db=quality.snr_db if quality else 0.0,
                dynamic_score=window.information_gain_bits,
                recommendation=_recommendation(window.rank, len(outcome.selection.selected)),
                rank=window.rank,
                information_gain_bits=window.information_gain_bits,
                cumulative_log_det=_finite(window.cumulative_log_det),
                n_rows=window.n_rows,
                missing_ratio=quality.missing_ratio if quality else None,
                anomaly_ratio=quality.anomaly_ratio if quality else None,
            )
        )
    return segments


def _recommendation(rank: int, total: int) -> str:
    """Rank-based, because the information gain is already ordered by construction."""

    if rank <= max(1, total // 3):
        return "strongly_recommended"
    if rank <= max(2, (2 * total) // 3):
        return "recommended"
    return "review"


def _series_projection(outcome: SegmentSelectionOutcome) -> dict[str, list[float | None]]:
    columns = [*outcome.input_columns, outcome.output_column]
    projection: dict[str, list[float | None]] = {}
    for column in columns:
        values = outcome.series.values[column][:MAX_RESPONSE_POINTS]
        projection[column] = [None if not np.isfinite(value) else float(value) for value in values]
    return projection


def _timestamp_at(timestamps: list[datetime], index: int) -> datetime | None:
    if 0 <= index < len(timestamps):
        return timestamps[index]
    return None


def _finite(value: float) -> float:
    return float(value) if np.isfinite(value) else 0.0


def selection_payload(outcome: SegmentSelectionOutcome) -> dict[str, Any]:
    """Compact JSON form used by the optimiser cache key and the report layer."""

    return {
        "selected_windows": [window.to_payload() for window in outcome.selection.selected],
        "gating": outcome.gating.to_payload(),
        "selection": outcome.selection.to_payload(),
        "input_columns": list(outcome.input_columns),
        "output_column": outcome.output_column,
    }
