"""Read and write immutable CSV artifacts for any persisted dataset version."""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from app.models.dataset import Dataset, DatasetVersion
from app.services.dataset_csv import DatasetCsvError, ParsedCsv, load_parsed_csv


class DatasetVersionArtifactError(Exception):
    """Raised when a version's registered immutable artifact cannot be read."""

    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def load_version_csv(
    *, dataset: Dataset, version: DatasetVersion, artifact_root: Path
) -> ParsedCsv:
    """Parse the exact CSV registered by a version, never the dataset's mutable active pointer."""

    encoding = _string_parameter(version.parameters, "csv_encoding") or dataset.encoding
    delimiter = _string_parameter(version.parameters, "csv_delimiter") or dataset.delimiter
    if encoding is None or delimiter is None:
        raise DatasetVersionArtifactError(
            "DATASET_ARTIFACT_MISSING", "数据版本缺少 CSV 解析元数据。"
        )
    try:
        return load_parsed_csv(
            artifact_root=artifact_root,
            relative_path=version.artifact_path,
            encoding=encoding,
            delimiter=delimiter,
        )
    except DatasetCsvError as error:
        raise DatasetVersionArtifactError(error.code, error.message, error.details) from error


def write_derived_csv(
    *,
    artifact_root: Path,
    dataset_id: UUID,
    version_id: UUID,
    headers: Sequence[str],
    timestamp_column: str,
    timestamps: Sequence[datetime],
    values: Mapping[str, Sequence[str | float | None]],
) -> tuple[str, str]:
    """Write a new immutable artifact once and return its relative path and digest."""

    # The timestamp column is regenerated from `timestamps` below rather than read from
    # `values`, so it is deliberately excluded from the alignment check.
    data_columns = [column for column in headers if column != timestamp_column]
    missing = [column for column in data_columns if column not in values]
    if missing:
        raise ValueError(f"derived CSV is missing columns: {missing}")
    if any(len(values[column]) != len(timestamps) for column in data_columns):
        raise ValueError("derived CSV columns must align with timestamps")
    relative_path = Path("derived") / str(dataset_id) / f"{version_id}.csv"
    destination = artifact_root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RuntimeError("derived dataset artifact path collision")
    with destination.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(headers)
        for index, timestamp in enumerate(timestamps):
            row = []
            for column in headers:
                if column == timestamp_column:
                    row.append(timestamp.isoformat())
                    continue
                row.append(_serialize_value(values[column][index]))
            writer.writerow(row)
    return relative_path.as_posix(), _sha256(destination)


def remove_derived_artifact(*, artifact_root: Path, relative_path: str) -> None:
    """Only used to roll back a failed, newly-created derived artifact."""

    (artifact_root / relative_path).unlink(missing_ok=True)


def _string_parameter(parameters: Mapping[str, Any], key: str) -> str | None:
    value = parameters.get(key)
    return value if isinstance(value, str) and value else None


def _serialize_value(value: str | float | None) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return format(value, ".12g")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
