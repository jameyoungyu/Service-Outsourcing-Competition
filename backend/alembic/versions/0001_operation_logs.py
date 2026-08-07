"""Create core operation log table.

Revision ID: 0001_operation_logs
Revises:
Create Date: 2026-07-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_operation_logs"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operation_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("subject_id", sa.String(length=64), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operation_logs_event_type", "operation_logs", ["event_type"])
    op.create_index("ix_operation_logs_request_id", "operation_logs", ["request_id"])
    op.create_index("ix_operation_logs_subject_id", "operation_logs", ["subject_id"])


def downgrade() -> None:
    op.drop_index("ix_operation_logs_subject_id", table_name="operation_logs")
    op.drop_index("ix_operation_logs_request_id", table_name="operation_logs")
    op.drop_index("ix_operation_logs_event_type", table_name="operation_logs")
    op.drop_table("operation_logs")
