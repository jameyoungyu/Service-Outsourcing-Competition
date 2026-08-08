"""Safe CSV staging, format detection and schema inference for uploaded datasets."""

from __future__ import annotations

import csv
import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import chardet
from algorithms.cleaning.quality import is_missing
from fastapi import UploadFile

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
DETECTION_SAMPLE_BYTES = 128 * 1024
ALLOWED_MIME_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "text/plain",
    "application/octet-stream",
}
TIME_HEADER_NAMES = {
    "time",
    "timestamp",
    "datetime",
    "date_time",
    "date",
    "时间",
    "日期",
    "时间戳",
}
INT_PATTERN = re.compile(r"^[+-]?\d+$")
FLOAT_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


class DatasetCsvError(Exception):
    """A client-safe parse failure converted into the uniform API error envelope."""

    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class StagedUpload:
    path: Path
    sha256: str
    byte_size: int
    filename: str
    encoding: str
    delimiter: str


@dataclass(frozen=True)
class ParsedCsv:
    headers: list[str]
    rows: list[dict[str, str]]
    inferred_types: dict[str, str]
    nullable: dict[str, bool]
    timestamp_column: str
    timestamps: list[datetime]
    preview_rows: list[dict[str, str | float | int | bool | None]]


async def stage_upload(upload: UploadFile, *, artifact_root: Path) -> StagedUpload:
    """Stream an upload to a private temporary file while enforcing the 100 MiB limit."""

    filename = upload.filename or "uploaded.csv"
    if Path(filename).suffix.lower() != ".csv":
        raise DatasetCsvError("DATASET_FILE_TYPE_INVALID", "仅支持 .csv 格式的数据文件。")
    if upload.content_type and upload.content_type.lower() not in ALLOWED_MIME_TYPES:
        raise DatasetCsvError(
            "DATASET_MIME_TYPE_INVALID",
            "上传文件的 MIME 类型不是受支持的 CSV 类型。",
            {"content_type": upload.content_type},
        )

    temporary_directory = artifact_root / "uploads" / ".tmp"
    temporary_directory.mkdir(parents=True, exist_ok=True)
    temporary_path = temporary_directory / f"{uuid4().hex}.upload"
    digest = hashlib.sha256()
    size = 0
    sample = bytearray()
    try:
        with temporary_path.open("wb") as destination:
            while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise DatasetCsvError(
                        "DATASET_FILE_TOO_LARGE",
                        "CSV 文件超过 100MB 上限。",
                        {"max_bytes": MAX_UPLOAD_BYTES},
                    )
                digest.update(chunk)
                if len(sample) < DETECTION_SAMPLE_BYTES:
                    remaining = DETECTION_SAMPLE_BYTES - len(sample)
                    sample.extend(chunk[:remaining])
                destination.write(chunk)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    if size == 0:
        temporary_path.unlink(missing_ok=True)
        raise DatasetCsvError("INVALID_DATASET_SCHEMA", "CSV 文件不能为空。")
    encoding = detect_encoding(bytes(sample))
    delimiter = detect_delimiter(bytes(sample), encoding)
    return StagedUpload(
        path=temporary_path,
        sha256=digest.hexdigest(),
        byte_size=size,
        filename=filename,
        encoding=encoding,
        delimiter=delimiter,
    )


def parse_csv(staged: StagedUpload) -> ParsedCsv:
    """Read and validate a staged CSV exactly once before it becomes an immutable asset."""

    try:
        with staged.path.open("r", encoding=staged.encoding, newline="") as source:
            reader = csv.reader(source, delimiter=staged.delimiter)
            raw_headers = next(reader, None)
            if raw_headers is None:
                raise DatasetCsvError("INVALID_DATASET_SCHEMA", "CSV 缺少表头。")
            headers = [header.strip().lstrip("\ufeff") for header in raw_headers]
            _validate_headers(headers)
            rows = _read_rows(reader, headers)
    except UnicodeDecodeError as error:
        raise DatasetCsvError(
            "CSV_ENCODING_UNSUPPORTED",
            "无法按识别到的编码读取 CSV 文件。",
            {"encoding": staged.encoding},
        ) from error
    except csv.Error as error:
        raise DatasetCsvError("INVALID_DATASET_SCHEMA", "CSV 语法无效。") from error

    if not rows:
        raise DatasetCsvError("INSUFFICIENT_ROWS", "CSV 至少需要一行有效数据。")
    for header in headers:
        if all(is_missing(row[header]) for row in rows):
            raise DatasetCsvError(
                "INVALID_DATASET_SCHEMA",
                "不允许存在整列为空的数据字段。",
                {"column": header},
            )

    timestamp_column = _resolve_timestamp_column(headers)
    timestamps = _parse_timestamps(rows, timestamp_column)
    inferred_types = {
        header: _infer_type([row[header] for row in rows], is_timestamp=header == timestamp_column)
        for header in headers
    }
    nullable = {header: any(is_missing(row[header]) for row in rows) for header in headers}
    preview_rows = [
        {header: _display_value(row[header], inferred_types[header]) for header in headers}
        for row in rows[:100]
    ]
    return ParsedCsv(
        headers=headers,
        rows=rows,
        inferred_types=inferred_types,
        nullable=nullable,
        timestamp_column=timestamp_column,
        timestamps=timestamps,
        preview_rows=preview_rows,
    )


def discard_staged_upload(staged: StagedUpload) -> None:
    staged.path.unlink(missing_ok=True)


def move_to_immutable_storage(staged: StagedUpload, *, artifact_root: Path, dataset_id: str) -> str:
    """Move a verified temporary file once; existing raw files are never overwritten."""

    relative_path = Path("uploads") / f"{dataset_id}_raw.csv"
    destination = artifact_root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RuntimeError("dataset raw artifact path collision")
    staged.path.replace(destination)
    return relative_path.as_posix()


def load_parsed_csv(
    *, artifact_root: Path, relative_path: str, encoding: str, delimiter: str
) -> ParsedCsv:
    """Reparse a stored raw file for preview/profile recomputation without mutation."""

    raw_path = artifact_root / relative_path
    if not raw_path.is_file():
        raise DatasetCsvError("DATASET_ARTIFACT_MISSING", "数据集原始文件不存在。")
    return parse_csv(
        StagedUpload(
            path=raw_path,
            sha256="",
            byte_size=raw_path.stat().st_size,
            filename=raw_path.name,
            encoding=encoding,
            delimiter=delimiter,
        )
    )


def detect_encoding(sample: bytes) -> str:
    detected = chardet.detect(sample)
    candidate = str(detected.get("encoding") or "utf-8").lower().replace("_", "-")
    if candidate == "ascii":
        return "utf-8"
    if candidate in {"utf-8", "utf-8-sig"}:
        return "utf-8-sig"
    if candidate in {"gbk", "gb2312", "gb18030"}:
        return "gb18030"
    # Short GBK/GB2312 CSV headers are occasionally misidentified as Latin-1
    # by chardet because their ASCII body dominates the sample. Prefer the GB
    # decoder only when it reveals actual CJK text, preserving genuine Latin CSV.
    if candidate.startswith(("iso-8859", "windows-125")) and any(byte >= 0x80 for byte in sample):
        try:
            gb_text = sample.decode("gb18030")
        except UnicodeDecodeError:
            gb_text = ""
        if any("\u4e00" <= character <= "\u9fff" for character in gb_text):
            return "gb18030"
    try:
        sample.decode(candidate)
    except (LookupError, UnicodeDecodeError) as error:
        raise DatasetCsvError(
            "CSV_ENCODING_UNSUPPORTED",
            "无法识别 CSV 文件编码；请使用 UTF-8、GBK 或 GB2312。",
        ) from error
    return candidate


def detect_delimiter(sample: bytes, encoding: str) -> str:
    try:
        decoded = sample.decode(encoding)
        dialect = csv.Sniffer().sniff(decoded, delimiters=",;\t")
        return dialect.delimiter
    except (csv.Error, UnicodeDecodeError):
        return ","


def parse_timestamp(value: str) -> datetime:
    """Support ISO 8601, common industrial formats and Unix seconds/milliseconds."""

    normalized = value.strip()
    if FLOAT_PATTERN.fullmatch(normalized):
        numeric = float(normalized)
        if abs(numeric) > 10_000_000_000:
            numeric /= 1_000
        try:
            return datetime.fromtimestamp(numeric, tz=UTC)
        except (OverflowError, OSError, ValueError) as error:
            raise ValueError("invalid unix timestamp") from error
    iso_value = normalized.replace("Z", "+00:00")
    try:
        result = datetime.fromisoformat(iso_value)
    except ValueError:
        result = _parse_common_timestamp(normalized)
    if result.tzinfo is None:
        return result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _parse_common_timestamp(value: str) -> datetime:
    for pattern in (
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            continue
    raise ValueError("unsupported timestamp format")


def _validate_headers(headers: list[str]) -> None:
    if not headers or any(not header for header in headers):
        raise DatasetCsvError("INVALID_DATASET_SCHEMA", "CSV 表头不能为空。")
    duplicates = sorted({header for header in headers if headers.count(header) > 1})
    if duplicates:
        raise DatasetCsvError(
            "INVALID_DATASET_SCHEMA",
            "CSV 表头不能包含重复列名。",
            {"duplicate_columns": duplicates},
        )


def _read_rows(reader: Iterable[list[str]], headers: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line_number, values in enumerate(reader, start=2):
        if not values or all(not value.strip() for value in values):
            continue
        if len(values) != len(headers):
            raise DatasetCsvError(
                "INVALID_DATASET_SCHEMA",
                "CSV 数据行字段数量与表头不一致。",
                {
                    "line": line_number,
                    "expected_columns": len(headers),
                    "actual_columns": len(values),
                },
            )
        rows.append(dict(zip(headers, (value.strip() for value in values), strict=True)))
    return rows


def _resolve_timestamp_column(headers: list[str]) -> str:
    candidates = [header for header in headers if _looks_like_time_header(header)]
    if not candidates:
        raise DatasetCsvError(
            "INVALID_DATASET_SCHEMA",
            "未找到时间戳列；请使用 time、timestamp、datetime 或中文时间列名。",
        )
    if len(candidates) > 1:
        raise DatasetCsvError(
            "INVALID_DATASET_SCHEMA",
            "检测到多个候选时间戳列，请仅保留一个时间列。",
            {"candidates": candidates},
        )
    return candidates[0]


def _looks_like_time_header(header: str) -> bool:
    normalized = header.strip().lower().replace(" ", "_").replace("-", "_")
    return (
        normalized in TIME_HEADER_NAMES
        or normalized.endswith("_time")
        or normalized.endswith("_timestamp")
        or "时间" in header
        or "日期" in header
    )


def _parse_timestamps(rows: list[dict[str, str]], column: str) -> list[datetime]:
    parsed: list[datetime] = []
    for row_number, row in enumerate(rows, start=2):
        raw_value = row[column]
        if is_missing(raw_value):
            raise DatasetCsvError(
                "TIMESTAMP_PARSE_FAILED",
                "时间戳列不允许缺失。",
                {"column": column, "line": row_number},
            )
        try:
            parsed.append(parse_timestamp(raw_value))
        except ValueError as error:
            raise DatasetCsvError(
                "TIMESTAMP_PARSE_FAILED",
                "无法解析时间戳列。",
                {"column": column, "line": row_number, "value": raw_value},
            ) from error
    return parsed


def _infer_type(values: list[str], *, is_timestamp: bool) -> str:
    non_missing = [value for value in values if not is_missing(value)]
    if is_timestamp:
        return "datetime"
    normalized = [value.strip().lower() for value in non_missing]
    if normalized and all(value in {"true", "false", "0", "1"} for value in normalized):
        return "boolean"
    if normalized and all(INT_PATTERN.fullmatch(value) for value in normalized):
        return "integer"
    if normalized and all(FLOAT_PATTERN.fullmatch(value) for value in normalized):
        return "float"
    return "string"


def _display_value(value: str, inferred_type: str) -> str | float | int | bool | None:
    if is_missing(value):
        return None
    if inferred_type == "datetime":
        return parse_timestamp(value).isoformat()
    if inferred_type == "integer":
        return int(value)
    if inferred_type == "float":
        return float(value)
    if inferred_type == "boolean":
        return value.strip().lower() in {"true", "1"}
    return value
