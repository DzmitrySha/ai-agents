"""Usage analytics: tool calls and API requests.

Revision ID: 005_usage_events
Revises: 004_app_settings
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_usage_events"
down_revision: str | None = "004_app_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usage_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "ts", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("agent_slug", sa.String(length=64), nullable=True),
        sa.Column("tool_slug", sa.String(length=64), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("principal_kind", sa.String(length=16), nullable=False),
        sa.Column("principal_id", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=True),
        sa.Column("path", sa.String(length=200), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_kind_ts", "usage_events", ["kind", "ts"])
    op.create_index("ix_usage_agent_ts", "usage_events", ["agent_slug", "ts"])
    op.create_index("ix_usage_tool_ts", "usage_events", ["tool_slug", "ts"])
    op.create_index("ix_usage_path_ts", "usage_events", ["path", "ts"])


def downgrade() -> None:
    op.drop_index("ix_usage_path_ts", table_name="usage_events")
    op.drop_index("ix_usage_tool_ts", table_name="usage_events")
    op.drop_index("ix_usage_agent_ts", table_name="usage_events")
    op.drop_index("ix_usage_kind_ts", table_name="usage_events")
    op.drop_table("usage_events")
