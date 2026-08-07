"""Uniform numeric access to any dataset version, uploaded or simulated.

Every stage from segment selection onwards needs the same thing: the numeric arrays of
one immutable version, plus which columns are inputs and which is the output. Uploaded
CSVs carry that in PostgreSQL (``DatasetVersion`` + ``DatasetColumn``); the S1-S6
benchmarks carry it in a local artifact manifest. This module hides the difference so the
closed loop never has to care which kind of data it is running on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import median
from uuid import UUID

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset, DatasetColumn, DatasetVersion
from app.services.dataset_version_io import DatasetVersionArtifactError, load_version_csv
from app.services.simulation_service import (
    SimulationArtifactNotFoundError,
    load_simulation_by_version,
)

FloatArray = NDArray[np.float64]

MISSING_TOKENS = {"", "na", "n/a", "null", "none", "nan"}


class VersionDataError(Exception):
    """A client-safe failure to resolve a version into modelling-ready arrays."""

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
class VersionSeries:
    """Numeric view of one immutable dataset version."""

    dataset_id: UUID
    version_id: UUID
    dataset_name: str
    origin: str
    timestamps: list[datetime]
    values: dict[str, FloatArray]
    declared_inputs: tuple[str, ...]
    declared_output: str | None
    sample_period_seconds: float | None

    @property
    def n_samples(self) -> int:
        return len(self.timestamps) if self.timestamps else _first_length(self.values)

    def numeric_columns(self) -> list[str]:
        return sorted(self.values)

    def resolve_columns(
        self,
        *,
        input_columns: list[str] | None,
        output_column: str | None,
    ) -> tuple[list[str], str]:
        """Pick the modelling roles, preferring the request then the stored schema."""

        resolved_output = output_column or self.declared_output
        if resolved_output is None:
            raise VersionDataError(
                "INVALID_DATASET_SCHEMA",
                "未指定输出变量，且数据版本没有已确认的输出列。",
                details={"available_columns": self.numeric_columns()},
            )
        if resolved_output not in self.values:
            raise VersionDataError(
                "INVALID_DATASET_SCHEMA",
                "请求的输出变量不存在或不是数值列。",
                details={
                    "output_column": resolved_output,
                    "available_columns": self.numeric_columns(),
                },
            )
        candidates = list(input_columns or self.declared_inputs)
        if not candidates:
            candidates = [column for column in self.numeric_columns() if column != resolved_output]
        invalid = sorted(set(candidates) - set(self.values))
        if invalid:
            raise VersionDataError(
                "INVALID_DATASET_SCHEMA",
                "请求的输入变量不存在或不是数值列。",
                details={"invalid_columns": invalid, "available_columns": self.numeric_columns()},
            )
        if resolved_output in candidates:
            raise VersionDataError(
                "INVALID_DATASET_SCHEMA",
                "同一列不能同时作为输入和输出。",
                details={"column": resolved_output},
            )
        if not candidates:
            raise VersionDataError(
                "INVALID_DATASET_SCHEMA",
                "数据版本不包含可用的输入变量。",
                details={"available_columns": self.numeric_columns()},
            )
        return candidates, resolved_output


async def load_version_series(
    session: AsyncSession,
    *,
    version_id: UUID,
    artifact_root: Path,
    dataset_id: UUID | None = None,
) -> VersionSeries:
    """Resolve a version id to numeric arrays, trying the database then local artifacts."""

    version = await session.get(DatasetVersion, version_id)
    if version is not None:
        return await _load_persisted_version(
            session,
            version=version,
            artifact_root=artifact_root,
            dataset_id=dataset_id,
        )
    return _load_simulation_version(
        version_id=version_id,
        artifact_root=artifact_root,
        dataset_id=dataset_id,
    )


async def _load_persisted_version(
    session: AsyncSession,
    *,
    version: DatasetVersion,
    artifact_root: Path,
    dataset_id: UUID | None,
) -> VersionSeries:
    dataset = await session.get(Dataset, version.dataset_id)
    if dataset is None:
        raise VersionDataError("DATASET_NOT_FOUND", "数据版本所属数据集不存在。", status_code=404)
    if dataset_id is not None and dataset_id != dataset.id:
        raise VersionDataError(
            "DATASET_VERSION_MISMATCH",
            "数据集 ID 与数据版本不匹配。",
            details={"dataset_id": str(dataset_id), "version_id": str(version.id)},
        )
    try:
        parsed = load_version_csv(dataset=dataset, version=version, artifact_root=artifact_root)
    except DatasetVersionArtifactError as error:
        raise VersionDataError(
            error.code, error.message, status_code=404, details=error.details
        ) from error

    columns = list(
        (
            await session.scalars(
                select(DatasetColumn)
                .where(DatasetColumn.version_id == version.id)
                .order_by(DatasetColumn.position)
            )
        ).all()
    )
    numeric_names = [
        name
        for name in parsed.headers
        if name != parsed.timestamp_column and parsed.inferred_types.get(name) == "numeric"
    ]
    values = {name: _column_array(parsed.rows, name) for name in numeric_names}
    if not values:
        raise VersionDataError(
            "NO_NUMERIC_SIGNAL",
            "数据版本不包含可用于建模的数值列。",
            details={"headers": list(parsed.headers)},
        )
    declared_inputs = tuple(
        column.name for column in columns if column.role == "input" and column.name in values
    )
    declared_output = next(
        (column.name for column in columns if column.role == "output" and column.name in values),
        None,
    )
    return VersionSeries(
        dataset_id=dataset.id,
        version_id=version.id,
        dataset_name=dataset.name,
        origin="dataset",
        timestamps=list(parsed.timestamps),
        values=values,
        declared_inputs=declared_inputs,
        declared_output=declared_output,
        sample_period_seconds=_median_period(parsed.timestamps),
    )


def _load_simulation_version(
    *,
    version_id: UUID,
    artifact_root: Path,
    dataset_id: UUID | None,
) -> VersionSeries:
    try:
        simulated = load_simulation_by_version(version_id, artifact_root=artifact_root)
    except SimulationArtifactNotFoundError as error:
        raise VersionDataError(
            "DATASET_VERSION_NOT_FOUND",
            "数据版本不存在，且不是本地仿真产物。",
            status_code=404,
            details={"version_id": str(version_id)},
        ) from error
    if dataset_id is not None and dataset_id != simulated.dataset_id:
        raise VersionDataError(
            "DATASET_VERSION_MISMATCH",
            "数据集 ID 与数据版本不匹配。",
            details={"dataset_id": str(dataset_id), "version_id": str(version_id)},
        )
    values = {name: np.asarray(array, dtype=float) for name, array in simulated.values.items()}
    inputs = tuple(sorted(name for name in values if name.startswith("u")))
    output = "y" if "y" in values else None
    return VersionSeries(
        dataset_id=simulated.dataset_id,
        version_id=simulated.version_id,
        dataset_name=simulated.dataset_name,
        origin="simulation",
        timestamps=[],
        values=values,
        declared_inputs=inputs,
        declared_output=output,
        sample_period_seconds=None,
    )


def _column_array(rows: list[dict[str, str]], column: str) -> FloatArray:
    """Missing tokens become NaN rather than zero; downstream tools drop, never impute."""

    values = np.empty(len(rows), dtype=float)
    for index, row in enumerate(rows):
        raw = row.get(column)
        if raw is None or raw.strip().lower() in MISSING_TOKENS:
            values[index] = np.nan
            continue
        try:
            values[index] = float(raw)
        except ValueError:
            values[index] = np.nan
    return values


def _median_period(timestamps: list[datetime]) -> float | None:
    if len(timestamps) < 2:
        return None
    deltas = [
        (later - earlier).total_seconds()
        for earlier, later in zip(timestamps, timestamps[1:], strict=False)
        if (later - earlier).total_seconds() > 0
    ]
    return float(median(deltas)) if deltas else None


def _first_length(values: dict[str, FloatArray]) -> int:
    for array in values.values():
        return int(array.shape[0])
    return 0
