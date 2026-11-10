"""Add per-run harness snapshot and fingerprint.

Revision ID: 014_run_harness_snapshot
Revises: 013_rename_runs_write_scope
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "014_run_harness_snapshot"
down_revision: str | None = "013_rename_runs_write_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("harness_snapshot", sa.JSON(), nullable=True))
    op.add_column("runs", sa.Column("harness_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "harness_hash")
    op.drop_column("runs", "harness_snapshot")
