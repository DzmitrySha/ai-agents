"""Add sub-agent runs and agent allowlists.

Revision ID: 020_subruns
Revises: 019_delivery_outbox
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "020_subruns"
down_revision: str | None = "019_delivery_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("parent_run_id", sa.String(length=36), nullable=True))
    op.add_column(
        "runs",
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_foreign_key(
        "fk_runs_parent_run_id",
        "runs",
        "runs",
        ["parent_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_runs_parent_run_id", "runs", ["parent_run_id"])
    op.add_column(
        "agents",
        sa.Column("sub_agents", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("agents", "sub_agents")
    op.drop_index("ix_runs_parent_run_id", table_name="runs")
    op.drop_constraint("fk_runs_parent_run_id", "runs", type_="foreignkey")
    op.drop_column("runs", "depth")
    op.drop_column("runs", "parent_run_id")
