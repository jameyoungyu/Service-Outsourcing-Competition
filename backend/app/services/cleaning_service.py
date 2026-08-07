"""Persisted preprocessing orchestration for immutable dataset-version derivation."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from uuid import UUID, uuid4

from algorithms.cleaning.pipeline import (
    CleaningContext,
    CleaningParameters,
    CleaningPipeline,
    CleaningResult,
)
from algorithms.cleaning.quality import build_quality_profile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import (
    Dataset,
    DatasetColumn,
    DatasetProfileRecord,
    DatasetVersion,
    ProcessingRun,
)
from app.models.operation_log import OperationLog
from app.schemas.preprocessing import CleanData, CleanRequest, CleanSeries
from app.services.contract_stubs import completed_task
from app.services.dataset_version_io import (
    DatasetVersionArtifactError,
    load_version_csv,
    remove_derived_artifact,
    write_derived_csv,
)

MAX_RESPONSE_POINTS = 10_000


class CleaningDomainError(Exception):
    """A client-safe preprocessing error for the standard API error envelope."""

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


async def clean_dataset_version(
    session: AsyncSession,
    *,
    payload: CleanRequest,
    artifact_root: Path,
) -> CleanData:
    """Run the pure pipeline and atomically register a new immutable derived version."""

    source_version = await session.get(DatasetVersion, payload.version_id)
    if source_version is None:
        raise CleaningDomainError(
            "DATASET_VERSION_NOT_FOUND", "待清洗的数据版本不存在。", status_code=404
        )
    dataset = await session.get(Dataset, source_version.dataset_id)
    if dataset is None:
        raise CleaningDomainError(
            "DATASET_NOT_FOUND", "数据版本所属数据集不存在。", status_code=404
        )
    if payload.dataset_id is not None and payload.dataset_id != dataset.id:
        raise CleaningDomainError(
            "DATASET_VERSION_MISMATCH",
            "请求的数据集 ID 不属于给定版本。",
            details={"dataset_id": str(payload.dataset_id), "version_id": str(payload.version_id)},
        )
    source_columns = await _version_columns(session, source_version.id)
    if not source_columns:
        raise CleaningDomainError("INVALID_DATASET_SCHEMA", "数据版本缺少列元数据。")
    try:
        parsed = load_version_csv(
            dataset=dataset, version=source_version, artifact_root=artifact_root
        )
    except DatasetVersionArtifactError as error:
        raise CleaningDomainError(
            error.code, error.message, status_code=404, details=error.details
        ) from error

    parameters = _resolve_parameters(payload)
    context = CleaningContext(
        headers=parsed.headers,
        timestamp_column=parsed.timestamp_column,
        timestamps=parsed.timestamps,
        rows=parsed.rows,
        inferred_types=parsed.inferred_types,
    )
    result = CleaningPipeline().execute(context, parameters)
    if not result.cleaned_numeric:
        raise CleaningDomainError("INVALID_DATASET_SCHEMA", "数据版本不包含可清洗的数值列。")

    derived_version_id = uuid4()
    artifact_path: str | None = None
    try:
        artifact_path, checksum = write_derived_csv(
            artifact_root=artifact_root,
            dataset_id=dataset.id,
            version_id=derived_version_id,
            headers=parsed.headers,
            timestamp_column=parsed.timestamp_column,
            timestamps=result.timestamps,
            values=result.values,
        )
        derived_version = DatasetVersion(
            id=derived_version_id,
            dataset_id=dataset.id,
            parent_version_id=source_version.id,
            version_index=await _next_version_index(session, dataset.id),
            name="",
            operation_name="preprocessing.clean",
            parameters=_version_parameters(payload, parameters, result, source_version.id),
            artifact_path=artifact_path,
            sha256=checksum,
            row_count=len(result.timestamps),
            column_count=len(parsed.headers),
            time_range_start=min(result.timestamps),
            time_range_end=max(result.timestamps),
            created_at=datetime.now(UTC),
        )
        derived_version.name = f"V{derived_version.version_index} · 清洗规整"
        derived_parsed = load_version_csv(
            dataset=dataset,
            version=derived_version,
            artifact_root=artifact_root,
        )
        profile_payload = build_quality_profile(
            dataset_id=str(dataset.id),
            version_id=str(derived_version.id),
            headers=derived_parsed.headers,
            rows=derived_parsed.rows,
            inferred_types=derived_parsed.inferred_types,
            timestamps=derived_parsed.timestamps,
        ).payload
        copied_columns = _clone_columns(
            source_columns,
            dataset_id=dataset.id,
            version_id=derived_version.id,
            nullable=derived_parsed.nullable,
        )
        now = datetime.now(UTC)
        profile = DatasetProfileRecord(
            id=uuid4(),
            dataset_id=dataset.id,
            version_id=derived_version.id,
            quality_score=float(profile_payload["quality_score"]),
            profile=profile_payload,
            created_at=now,
            updated_at=now,
        )
        run = ProcessingRun(
            id=uuid4(),
            dataset_id=dataset.id,
            source_version_id=source_version.id,
            run_type="preprocessing.clean",
            status="succeeded",
            parameters=_jsonable_parameters(parameters),
            result={
                "derived_version_id": str(derived_version.id),
                "total_cleaned_points": result.total_changed_points,
                "outlier_counts": {
                    column: len(indices)
                    for column, indices in result.detected_outlier_indices.items()
                },
                "frozen_segment_count": len(result.frozen_segments),
                "warnings": result.warnings,
            },
            created_at=now,
            finished_at=now,
        )
        audit = OperationLog(
            id=uuid4(),
            event_type="preprocessing.clean.completed",
            subject_id=str(dataset.id),
            payload_json=json.dumps(
                {
                    "source_version_id": str(source_version.id),
                    "derived_version_id": str(derived_version.id),
                    "algorithm": CleaningPipeline.name,
                    "parameters": _jsonable_parameters(parameters),
                    "total_cleaned_points": result.total_changed_points,
                    "replaced_indices": result.changed_indices,
                    "executed_at": now.isoformat(),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            created_at=now,
        )
        dataset.active_version_id = derived_version.id
        dataset.updated_at = now
        session.add(derived_version)
        await session.flush()
        session.add_all([*copied_columns, profile, run, audit])
        await session.commit()
    except Exception:
        await session.rollback()
        if artifact_path is not None:
            remove_derived_artifact(artifact_root=artifact_root, relative_path=artifact_path)
        raise

    return _clean_data(
        dataset_id=dataset.id,
        source_version_id=source_version.id,
        derived_version_id=derived_version_id,
        source_columns=source_columns,
        result=result,
    )


async def _version_columns(session: AsyncSession, version_id: UUID) -> list[DatasetColumn]:
    return list(
        (
            await session.scalars(
                select(DatasetColumn)
                .where(DatasetColumn.version_id == version_id)
                .order_by(DatasetColumn.position)
            )
        ).all()
    )


async def _next_version_index(session: AsyncSession, dataset_id: UUID) -> int:
    current = await session.scalar(
        select(func.max(DatasetVersion.version_index)).where(
            DatasetVersion.dataset_id == dataset_id
        )
    )
    return int(current or 0) + 1


def _resolve_parameters(payload: CleanRequest) -> CleaningParameters:
    interpolation_value = payload.interpolation_method or payload.interpolation
    interpolation = {
        "forward_fill": "ffill",
        "backward_fill": "bfill",
    }.get(interpolation_value, interpolation_value)
    outlier_value = payload.outlier_method or payload.anomaly_detector
    detector = {"zscore": "z_score"}.get(outlier_value, outlier_value)
    return CleaningParameters(
        resample_period_seconds=(
            payload.resample_period_s
            if payload.resample_period_s is not None
            else payload.target_sample_period_seconds
        ),
        interpolation=interpolation,  # type: ignore[arg-type]
        max_consecutive_missing=payload.max_consecutive_missing,
        duplicate_strategy=payload.duplicate_strategy,
        outlier_detector=detector,  # type: ignore[arg-type]
        outlier_strategy=payload.anomaly_strategy,
        hampel_window=payload.hampel_window,
        hampel_threshold=(
            payload.hampel_n_sigmas
            if payload.hampel_n_sigmas is not None
            else payload.hampel_threshold
        ),
        z_score_threshold=payload.z_score_threshold,
        smoothing=payload.smoothing,
        smoothing_window=payload.smoothing_window,
    )


def _clone_columns(
    source_columns: Sequence[DatasetColumn],
    *,
    dataset_id: UUID,
    version_id: UUID,
    nullable: dict[str, bool],
) -> list[DatasetColumn]:
    return [
        DatasetColumn(
            id=uuid4(),
            dataset_id=dataset_id,
            version_id=version_id,
            position=column.position,
            name=column.name,
            inferred_type=column.inferred_type,
            role=column.role,
            unit=column.unit,
            nullable=nullable.get(column.name, column.nullable),
        )
        for column in source_columns
    ]


def _version_parameters(
    payload: CleanRequest,
    parameters: CleaningParameters,
    result: CleaningResult,
    source_version_id: UUID,
) -> dict[str, object]:
    return {
        "algorithm": CleaningPipeline.name,
        "source_version_id": str(source_version_id),
        "request": payload.model_dump(mode="json", exclude_none=True),
        "resolved_parameters": _jsonable_parameters(parameters),
        "total_cleaned_points": result.total_changed_points,
        "detected_outlier_counts": {
            column: len(indices) for column, indices in result.detected_outlier_indices.items()
        },
        "frozen_segment_count": len(result.frozen_segments),
        "warnings": result.warnings,
        "csv_encoding": "utf-8",
        "csv_delimiter": ",",
    }


def _jsonable_parameters(parameters: CleaningParameters) -> dict[str, object]:
    return asdict(parameters)


def _clean_data(
    *,
    dataset_id: UUID,
    source_version_id: UUID,
    derived_version_id: UUID,
    source_columns: Sequence[DatasetColumn],
    result: CleaningResult,
) -> CleanData:
    series, downsample_factor = _series_projection(result)
    output_column = next(
        (column.name for column in source_columns if column.role == "output"),
        next(iter(result.cleaned_numeric)),
    )
    selected = next(item for item in series if item.column == output_column)
    return CleanData(
        source_version_id=source_version_id,
        derived_version_id=derived_version_id,
        task=completed_task(stage="preprocessing.clean", message="时间规整与数据清洗已完成。"),
        series=series,
        dataset_id=dataset_id,
        new_version_id=derived_version_id,
        raw_series=selected.raw_series,
        cleaned_series=selected.cleaned_series,
        replaced_indices=selected.replaced_indices,
        total_cleaned_points=result.total_changed_points,
        warnings=result.warnings,
        recommended_downsample_factor=downsample_factor,
    )


def _series_projection(result: CleaningResult) -> tuple[list[CleanSeries], int]:
    total = len(result.timestamps)
    factor = max(1, ceil(total / MAX_RESPONSE_POINTS))
    indices = list(range(0, total, factor))
    if indices and indices[-1] != total - 1:
        indices.append(total - 1)
    series: list[CleanSeries] = []
    for column, cleaned in result.cleaned_numeric.items():
        changed = set(result.changed_indices[column])
        series.append(
            CleanSeries(
                column=column,
                timestamps=[result.timestamps[index] for index in indices],
                raw_series=[result.raw_numeric[column][index] for index in indices],
                cleaned_series=[cleaned[index] for index in indices],
                replaced_indices=[
                    projected_index
                    for projected_index, source_index in enumerate(indices)
                    if source_index in changed
                ],
            )
        )
    return series, factor
