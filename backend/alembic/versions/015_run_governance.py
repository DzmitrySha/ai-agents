"""Add run governance: token usage, digest, idempotency, event archival.

Revision ID: 015_run_governance
Revises: 014_run_harness_snapshot
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "015_run_governance"
down_revision: str | None = "014_run_harness_snapshot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("prompt_tokens", sa.Integer(), nullable=True))
    op.add_column("runs", sa.Column("completion_tokens", sa.Integer(), nullable=True))
    op.add_column("runs", sa.Column("total_tokens", sa.Integer(), nullable=True))
    op.add_column("runs", sa.Column("digest", sa.JSON(), nullable=True))
    op.add_column(
        "runs", sa.Column("idempotency_key", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "runs",
        sa.Column("events_archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_runs_finished_at", "runs", ["finished_at"])
    op.create_index(
        "uq_runs_idempotency",
        "runs",
        ["principal_kind", "principal_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_runs_idempotency", table_name="runs")
    op.drop_index("ix_runs_finished_at", table_name="runs")
    op.drop_column("runs", "events_archived_at")
    op.drop_column("runs", "idempotency_key")
    op.drop_column("runs", "digest")
    op.drop_column("runs", "total_tokens")
    op.drop_column("runs", "completion_tokens")
    op.drop_column("runs", "prompt_tokens")
