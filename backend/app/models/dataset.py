"""Persistent data-asset, version-lineage and profile records."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Dataset(Base):
    """A user-visible data asset; its raw upload is immutable once registered."""

    __tablename__ = "datasets"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="upload")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    raw_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    raw_path: Mapped[str] = mapped_column(String(512), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    encoding: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delimiter: Mapped[str | None] = mapped_column(String(8), nullable=True)
    active_version_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DatasetVersion(Base):
    """An immutable version node. Processing stages will append derived nodes later."""

    __tablename__ = "dataset_versions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_version_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    version_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    operation_name: Mapped[str] = mapped_column(String(80), nullable=False, default="raw_upload")
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    artifact_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False)
    time_range_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    time_range_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DatasetColumn(Base):
    """Schema and human-confirmed semantic role of one version column."""

    __tablename__ = "dataset_columns"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    inferred_type: Mapped[str] = mapped_column(String(32), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="ignore")
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nullable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class DatasetProfileRecord(Base):
    """Persisted quality diagnostics for one immutable dataset version."""

    __tablename__ = "dataset_profiles"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    quality_score: Mapped[float] = mapped_column(nullable=False)
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ProcessingRun(Base):
    """Auditable processing execution shell used by later pipeline stages."""

    __tablename__ = "processing_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=True, index=True
    )
    source_version_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    run_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="succeeded")
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
