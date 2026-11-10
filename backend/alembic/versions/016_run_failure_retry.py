"""Add run failure taxonomy and retry attempts.

Revision ID: 016_run_failure_retry
Revises: 015_run_governance
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "016_run_failure_retry"
down_revision: str | None = "015_run_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("failure_kind", sa.String(length=32), nullable=True))
    op.add_column("runs", sa.Column("attempts", sa.Integer(), nullable=True))
    op.create_index(
        "ix_runs_failure_kind_created", "runs", ["failure_kind", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_runs_failure_kind_created", table_name="runs")
    op.drop_column("runs", "attempts")
    op.drop_column("runs", "failure_kind")
