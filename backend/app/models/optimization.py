"""Closed-loop optimisation studies, trials and the cross-dataset strategy memory."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OptimizationStudy(Base):
    """One closed-loop search over preprocessing and model-structure parameters."""

    __tablename__ = "optimization_studies"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    objective: Mapped[str] = mapped_column(String(64), nullable=False, default="free_run_fit")
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    best_trial_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    best_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    fingerprint: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    # Cache-hit and pruning statistics; the phase-8 acceptance criteria are measured here.
    statistics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    warm_started_from: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OptimizationTrialRecord(Base):
    """One evaluated parameter combination, kept whether it succeeded or failed.

    Failed and pruned trials are persisted on purpose: hiding them would misrepresent how
    the search actually behaved, and the brief forbids concealing failed trials.
    """

    __tablename__ = "optimization_trials"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    study_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("optimization_studies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trial_number: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="complete")
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    cache_hit: Mapped[bool] = mapped_column(nullable=False, default=False)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StrategyMemory(Base):
    """A completed search, indexed by a data-profile fingerprint for warm starting.

    This is the mechanism behind the brief's "self-evolving" requirement: a run on one
    dataset leaves behind a reusable prior, so a later run on a similar process starts
    from what already worked instead of from the middle of the search space.

    Only parameters and train/validation metrics are stored. Test-set information is
    deliberately excluded, and a dataset is never warm-started from its own history.
    """

    __tablename__ = "strategy_memory"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    study_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    fingerprint: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    fingerprint_vector: Mapped[list[float]] = mapped_column(JSON, nullable=False, default=list)
    best_params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    achieved_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    objective_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="study")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
