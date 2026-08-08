"""Database-backed dataset asset management and quality-profile orchestration."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from algorithms.cleaning.quality import build_quality_profile
from fastapi import UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import (
    Dataset as DatasetModel,
)
from app.models.dataset import (
    DatasetColumn as DatasetColumnModel,
)
from app.models.dataset import (
    DatasetProfileRecord,
    ProcessingRun,
)
from app.models.dataset import (
    DatasetVersion as DatasetVersionModel,
)
from app.schemas.common import PageInfo
from app.schemas.datasets import (
    DatasetColumn,
    DatasetColumnConfig,
    DatasetConfigData,
    DatasetConfigRequest,
    DatasetDetail,
    DatasetListData,
    DatasetProfile,
    DatasetSummary,
    DatasetVersionsData,
    VersionEdge,
    VersionNode,
)
from app.services.dataset_csv import (
    DatasetCsvError,
    ParsedCsv,
    discard_staged_upload,
    move_to_immutable_storage,
    parse_csv,
    stage_upload,
)
from app.services.dataset_version_io import DatasetVersionArtifactError, load_version_csv


class DatasetDomainError(Exception):
    """Domain error that maps directly to the project-standard API envelope."""

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
class UploadedDataset:
    summary: DatasetSummary
    deduplicated: bool


async def upload_csv_dataset(
    session: AsyncSession,
    *,
    upload: UploadFile,
    display_name: str | None,
    artifact_root: Path,
) -> UploadedDataset:
    """Persist a validated raw upload and its first immutable V0/profile records."""

    try:
        staged = await stage_upload(upload, artifact_root=artifact_root)
        parsed = parse_csv(staged)
    except DatasetCsvError as error:
        raise DatasetDomainError(error.code, error.message, details=error.details) from error

    try:
        existing = await session.scalar(
            select(DatasetModel).where(DatasetModel.raw_sha256 == staged.sha256)
        )
        if existing is not None:
            discard_staged_upload(staged)
            return UploadedDataset(
                summary=await _dataset_summary(session, existing), deduplicated=True
            )

        dataset_id = uuid4()
        raw_path = move_to_immutable_storage(
            staged,
            artifact_root=artifact_root,
            dataset_id=str(dataset_id),
        )
        created_at = datetime.now(UTC)
        dataset = DatasetModel(
            id=dataset_id,
            name=_display_name(display_name, staged.filename),
            source="upload",
            status="ready",
            raw_sha256=staged.sha256,
            raw_path=raw_path,
            byte_size=staged.byte_size,
            encoding=staged.encoding,
            delimiter=staged.delimiter,
            created_at=created_at,
            updated_at=created_at,
        )
        version = DatasetVersionModel(
            id=uuid4(),
            dataset_id=dataset.id,
            version_index=0,
            name="V0 · 原始上传",
            operation_name="raw_upload",
            parameters={
                "encoding": staged.encoding,
                "delimiter": _delimiter_label(staged.delimiter),
                "original_filename": staged.filename,
            },
            artifact_path=raw_path,
            sha256=staged.sha256,
            row_count=len(parsed.rows),
            column_count=len(parsed.headers),
            time_range_start=min(parsed.timestamps),
            time_range_end=max(parsed.timestamps),
            created_at=created_at,
        )
        dataset.active_version_id = version.id
        columns = [
            DatasetColumnModel(
                id=uuid4(),
                dataset_id=dataset.id,
                version_id=version.id,
                position=position,
                name=header,
                inferred_type=parsed.inferred_types[header],
                role="timestamp" if header == parsed.timestamp_column else "ignore",
                nullable=parsed.nullable[header],
            )
            for position, header in enumerate(parsed.headers)
        ]
        profile = _build_profile(dataset.id, version.id, parsed)
        profile_record = DatasetProfileRecord(
            id=uuid4(),
            dataset_id=dataset.id,
            version_id=version.id,
            quality_score=float(profile["quality_score"]),
            profile=profile,
            created_at=created_at,
            updated_at=created_at,
        )
        # The ORM models intentionally avoid mutable relationships. Flush V0
        # before dependent metadata so PostgreSQL can enforce every FK.
        session.add_all([dataset, version])
        await session.flush()
        session.add_all([*columns, profile_record])
        await session.commit()
        await session.refresh(dataset)
        return UploadedDataset(summary=await _dataset_summary(session, dataset), deduplicated=False)
    except Exception:
        await session.rollback()
        # A transaction failure after the move must not leave a mutable orphan in uploads/.
        if "raw_path" in locals():
            (artifact_root / raw_path).unlink(missing_ok=True)
        raise
    finally:
        # No-op after a successful move; removes a temporary file for early failures.
        if "staged" in locals():
            discard_staged_upload(staged)


async def list_dataset_summaries(
    session: AsyncSession, *, page: int, page_size: int
) -> DatasetListData:
    total = int(await session.scalar(select(func.count()).select_from(DatasetModel)) or 0)
    records = list(
        (
            await session.scalars(
                select(DatasetModel)
                .order_by(DatasetModel.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return DatasetListData(
        items=[await _dataset_summary(session, record) for record in records],
        page=PageInfo(page=page, page_size=page_size, total=total),
    )


async def get_dataset_detail(
    session: AsyncSession, *, dataset_id: UUID, artifact_root: Path
) -> DatasetDetail:
    dataset = await _dataset_or_404(session, dataset_id)
    version = await _active_version_or_error(session, dataset)
    columns = await _version_columns(session, version.id)
    profile = await _profile_or_error(session, dataset.id, version.id)
    parsed = _load_version_csv(dataset, version, artifact_root)
    missing_counts = cast(dict[str, int], profile.profile.get("column_missing_counts", {}))
    return DatasetDetail(
        **(await _dataset_summary(session, dataset, columns=columns)).model_dump(),
        columns=[
            DatasetColumn(
                name=column.name,
                inferred_type=column.inferred_type,
                role=column.role,
                unit=column.unit,
                nullable=column.nullable,
                data_type=column.inferred_type,
                missing_count=int(missing_counts.get(column.name, 0)),
            )
            for column in columns
        ],
        time_range_start=version.time_range_start,
        time_range_end=version.time_range_end,
        preview={
            "columns": parsed.headers,
            "rows": parsed.preview_rows,
            "truncated": len(parsed.rows) > len(parsed.preview_rows),
            "recommended_downsample_factor": max(1, int((len(parsed.rows) + 9_999) / 10_000)),
        },
    )


async def delete_dataset_asset(session: AsyncSession, *, dataset_id: UUID) -> None:
    """Cascade-delete database metadata while deliberately retaining immutable raw evidence."""

    await _dataset_or_404(session, dataset_id)
    version_ids = select(DatasetVersionModel.id).where(DatasetVersionModel.dataset_id == dataset_id)
    await session.execute(
        delete(DatasetProfileRecord).where(DatasetProfileRecord.dataset_id == dataset_id)
    )
    await session.execute(
        delete(DatasetColumnModel).where(DatasetColumnModel.dataset_id == dataset_id)
    )
    await session.execute(delete(ProcessingRun).where(ProcessingRun.dataset_id == dataset_id))
    await session.execute(
        delete(DatasetVersionModel).where(DatasetVersionModel.id.in_(version_ids))
    )
    await session.execute(delete(DatasetModel).where(DatasetModel.id == dataset_id))
    await session.commit()


async def get_dataset_profile(session: AsyncSession, *, dataset_id: UUID) -> DatasetProfile:
    dataset = await _dataset_or_404(session, dataset_id)
    version = await _active_version_or_error(session, dataset)
    record = await _profile_or_error(session, dataset.id, version.id)
    return _profile_schema(record.profile)


async def get_dataset_versions(session: AsyncSession, *, dataset_id: UUID) -> DatasetVersionsData:
    dataset = await _dataset_or_404(session, dataset_id)
    versions = list(
        (
            await session.scalars(
                select(DatasetVersionModel)
                .where(DatasetVersionModel.dataset_id == dataset.id)
                .order_by(DatasetVersionModel.version_index, DatasetVersionModel.created_at)
            )
        ).all()
    )
    nodes = [
        VersionNode(
            id=version.id,
            name=version.name,
            tool=version.operation_name,
            created_at=version.created_at,
            parent_version_id=version.parent_version_id,
            parameters=version.parameters,
        )
        for version in versions
    ]
    edges = [
        VersionEdge(
            source=version.parent_version_id, target=version.id, operation=version.operation_name
        )
        for version in versions
        if version.parent_version_id is not None
    ]
    return DatasetVersionsData(
        dataset_id=dataset.id,
        active_version_id=dataset.active_version_id,
        nodes=nodes,
        edges=edges,
    )


async def configure_dataset_columns(
    session: AsyncSession,
    *,
    dataset_id: UUID,
    payload: DatasetConfigRequest,
    artifact_root: Path,
) -> DatasetConfigData:
    dataset = await _dataset_or_404(session, dataset_id)
    version = await _active_version_or_error(session, dataset)
    columns = await _version_columns(session, version.id)
    roles, units = _resolve_column_configuration(columns, payload)
    timestamp_columns = [name for name, role in roles.items() if role == "timestamp"]
    output_columns = [name for name, role in roles.items() if role == "output"]
    input_columns = [name for name, role in roles.items() if role == "input"]
    if len(timestamp_columns) != 1:
        raise DatasetDomainError("INVALID_DATASET_SCHEMA", "必须配置且只能配置一个时间戳列。")
    if len(output_columns) != 1:
        raise DatasetDomainError("INVALID_DATASET_SCHEMA", "MISO 配置必须且只能配置一个输出列。")
    if not input_columns:
        raise DatasetDomainError("INVALID_DATASET_SCHEMA", "至少需要配置一个输入列。")
    by_name = {column.name: column for column in columns}
    timestamp = timestamp_columns[0]
    if by_name[timestamp].inferred_type != "datetime":
        raise DatasetDomainError(
            "TIMESTAMP_PARSE_FAILED", "指定的时间列不是可解析的 datetime 字段。"
        )
    for column in columns:
        column.role = roles[column.name]
        if column.name in units:
            column.unit = units[column.name]

    parsed = _load_version_csv(dataset, version, artifact_root)
    profile_payload = _build_profile(dataset.id, version.id, parsed)
    profile_record = await _profile_or_error(session, dataset.id, version.id)
    profile_record.profile = profile_payload
    profile_record.quality_score = float(profile_payload["quality_score"])
    profile_record.updated_at = datetime.now(UTC)
    dataset.updated_at = datetime.now(UTC)
    await session.commit()
    return DatasetConfigData(
        dataset=await get_dataset_detail(
            session, dataset_id=dataset.id, artifact_root=artifact_root
        ),
        profile=_profile_schema(profile_payload),
    )


async def _dataset_summary(
    session: AsyncSession,
    dataset: DatasetModel,
    *,
    columns: Sequence[DatasetColumnModel] | None = None,
) -> DatasetSummary:
    active_version = await _active_version_or_error(session, dataset)
    resolved_columns = (
        list(columns) if columns is not None else await _version_columns(session, active_version.id)
    )
    time_column = next(
        (column.name for column in resolved_columns if column.role == "timestamp"), None
    )
    input_columns = [column.name for column in resolved_columns if column.role == "input"]
    output_column = next(
        (column.name for column in resolved_columns if column.role == "output"), None
    )
    return DatasetSummary(
        id=dataset.id,
        name=dataset.name,
        source=dataset.source,
        status=dataset.status,
        row_count=active_version.row_count,
        column_count=active_version.column_count,
        latest_version_id=active_version.id,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
        version_id=active_version.id,
        file_size_bytes=dataset.byte_size,
        col_count=active_version.column_count,
        time_column=time_column,
        input_columns=input_columns,
        output_column=output_column,
    )


async def _dataset_or_404(session: AsyncSession, dataset_id: UUID) -> DatasetModel:
    record = await session.get(DatasetModel, dataset_id)
    if record is None:
        raise DatasetDomainError(
            "DATASET_NOT_FOUND",
            "数据集不存在或已删除。",
            status_code=404,
            details={"dataset_id": str(dataset_id)},
        )
    return record


async def _active_version_or_error(
    session: AsyncSession, dataset: DatasetModel
) -> DatasetVersionModel:
    if dataset.active_version_id is None:
        raise DatasetDomainError(
            "DATASET_VERSION_NOT_FOUND", "数据集没有激活版本。", status_code=404
        )
    version = await session.get(DatasetVersionModel, dataset.active_version_id)
    if version is None or version.dataset_id != dataset.id:
        raise DatasetDomainError(
            "DATASET_VERSION_NOT_FOUND", "数据集激活版本不存在。", status_code=404
        )
    return version


async def _version_columns(session: AsyncSession, version_id: UUID) -> list[DatasetColumnModel]:
    return list(
        (
            await session.scalars(
                select(DatasetColumnModel)
                .where(DatasetColumnModel.version_id == version_id)
                .order_by(DatasetColumnModel.position)
            )
        ).all()
    )


async def _profile_or_error(
    session: AsyncSession, dataset_id: UUID, version_id: UUID
) -> DatasetProfileRecord:
    record = await session.scalar(
        select(DatasetProfileRecord).where(
            DatasetProfileRecord.dataset_id == dataset_id,
            DatasetProfileRecord.version_id == version_id,
        )
    )
    if record is None:
        raise DatasetDomainError(
            "DATASET_PROFILE_NOT_FOUND", "数据集质量画像尚未生成。", status_code=404
        )
    return record


def _build_profile(dataset_id: UUID, version_id: UUID, parsed: ParsedCsv) -> dict[str, Any]:
    return build_quality_profile(
        dataset_id=str(dataset_id),
        version_id=str(version_id),
        headers=parsed.headers,
        rows=parsed.rows,
        inferred_types=parsed.inferred_types,
        timestamps=parsed.timestamps,
    ).payload


def _profile_schema(payload: dict[str, Any]) -> DatasetProfile:
    external = {key: value for key, value in payload.items() if key != "column_missing_counts"}
    return DatasetProfile.model_validate(external)


def _load_version_csv(
    dataset: DatasetModel, version: DatasetVersionModel, artifact_root: Path
) -> ParsedCsv:
    try:
        return load_version_csv(dataset=dataset, version=version, artifact_root=artifact_root)
    except DatasetVersionArtifactError as error:
        raise DatasetDomainError(
            error.code, error.message, status_code=404, details=error.details
        ) from error


def _resolve_column_configuration(
    columns: Sequence[DatasetColumnModel], payload: DatasetConfigRequest
) -> tuple[dict[str, str], dict[str, str | None]]:
    known_names = {column.name for column in columns}
    current_roles = {column.name: column.role for column in columns}
    units: dict[str, str | None] = {}
    if payload.columns is not None:
        roles = {name: "ignore" for name in known_names}
        _apply_explicit_columns(roles, units, payload.columns, known_names)
        return roles, units

    if payload.time_column is None and payload.output_column is None and not payload.input_columns:
        raise DatasetDomainError("INVALID_DATASET_SCHEMA", "请提供 columns 或紧凑列映射字段。")
    roles = current_roles.copy()
    if payload.time_column is not None:
        _ensure_known_column(payload.time_column, known_names)
        for name in roles:
            if roles[name] == "timestamp":
                roles[name] = "ignore"
        roles[payload.time_column] = "timestamp"
    if payload.output_column is not None:
        _ensure_known_column(payload.output_column, known_names)
        for name in roles:
            if roles[name] == "output":
                roles[name] = "ignore"
        roles[payload.output_column] = "output"
    for name in payload.input_columns:
        _ensure_known_column(name, known_names)
        roles[name] = "input"
    for name in payload.ignored_columns:
        _ensure_known_column(name, known_names)
        roles[name] = "ignore"
    return roles, units


def _apply_explicit_columns(
    roles: dict[str, str],
    units: dict[str, str | None],
    entries: Sequence[DatasetColumnConfig],
    known_names: set[str],
) -> None:
    seen: set[str] = set()
    for entry in entries:
        _ensure_known_column(entry.name, known_names)
        if entry.name in seen:
            raise DatasetDomainError("INVALID_DATASET_SCHEMA", "列配置中存在重复字段。")
        seen.add(entry.name)
        roles[entry.name] = _normalise_role(entry.role)
        units[entry.name] = entry.unit


def _ensure_known_column(name: str, known_names: set[str]) -> None:
    if name not in known_names:
        raise DatasetDomainError(
            "INVALID_DATASET_SCHEMA", "列配置引用了不存在的字段。", details={"column": name}
        )


def _normalise_role(role: str) -> str:
    return {"time": "timestamp", "ignored": "ignore"}.get(role, role)


def _display_name(display_name: str | None, filename: str) -> str:
    candidate = (display_name or filename).strip()
    return candidate[:120] or "uploaded.csv"


def _delimiter_label(delimiter: str) -> str:
    return {",": "comma", ";": "semicolon", "\t": "tab"}.get(delimiter, delimiter)
