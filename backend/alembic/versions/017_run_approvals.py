"""Add run tool approvals.

Revision ID: 017_run_approvals
Revises: 016_run_failure_retry
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "017_run_approvals"
down_revision: str | None = "016_run_failure_retry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "run_approvals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tool", sa.String(length=200), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=64), nullable=False),
    )
    op.create_index(
        "ix_run_approvals_run_status", "run_approvals", ["run_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_run_approvals_run_status", table_name="run_approvals")
    op.drop_table("run_approvals")
