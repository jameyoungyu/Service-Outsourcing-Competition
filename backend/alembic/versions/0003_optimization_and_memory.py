"""Create closed-loop optimisation studies, trials and the strategy memory.

Revision ID: 0003_optimization_and_memory
Revises: 0002_datasets_and_profiles
Create Date: 2026-08-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_optimization_and_memory"
down_revision: str | None = "0002_datasets_and_profiles"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "optimization_studies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=True),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("objective", sa.String(length=64), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("best_trial_number", sa.Integer(), nullable=True),
        sa.Column("best_value", sa.Float(), nullable=True),
        sa.Column("best_params", sa.JSON(), nullable=False),
        sa.Column("fingerprint", sa.JSON(), nullable=False),
        sa.Column("statistics", sa.JSON(), nullable=False),
        sa.Column("warm_started_from", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_optimization_studies_dataset_id", "optimization_studies", ["dataset_id"])
    op.create_index("ix_optimization_studies_version_id", "optimization_studies", ["version_id"])

    op.create_table(
        "optimization_trials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("trial_number", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["study_id"], ["optimization_studies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_optimization_trials_study_id", "optimization_trials", ["study_id"])

    op.create_table(
        "strategy_memory",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=True),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("study_id", sa.Uuid(), nullable=True),
        sa.Column("fingerprint", sa.JSON(), nullable=False),
        sa.Column("fingerprint_vector", sa.JSON(), nullable=False),
        sa.Column("best_params", sa.JSON(), nullable=False),
        sa.Column("achieved_metrics", sa.JSON(), nullable=False),
        sa.Column("objective_value", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_strategy_memory_dataset_id", "strategy_memory", ["dataset_id"])


def downgrade() -> None:
    op.drop_index("ix_strategy_memory_dataset_id", table_name="strategy_memory")
    op.drop_table("strategy_memory")
    op.drop_index("ix_optimization_trials_study_id", table_name="optimization_trials")
    op.drop_table("optimization_trials")
    op.drop_index("ix_optimization_studies_version_id", table_name="optimization_studies")
    op.drop_index("ix_optimization_studies_dataset_id", table_name="optimization_studies")
    op.drop_table("optimization_studies")
