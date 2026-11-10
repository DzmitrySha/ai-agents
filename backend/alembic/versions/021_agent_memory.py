"""Add opt-in agent memory.

Revision ID: 021_agent_memory
Revises: 020_subruns
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "021_agent_memory"
down_revision: str | None = "020_subruns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "memory_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.create_table(
        "agent_memories",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "agent_id",
            sa.String(length=36),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("principal_kind", sa.String(length=16), nullable=False),
        sa.Column("principal_id", sa.String(length=64), nullable=False),
        sa.Column("namespace", sa.String(length=200), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "agent_id",
            "principal_kind",
            "principal_id",
            "namespace",
            "key",
            name="uq_agent_memories_scope_key",
        ),
    )
    op.create_index(
        "ix_agent_memories_scope",
        "agent_memories",
        ["agent_id", "principal_kind", "principal_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_memories_scope", table_name="agent_memories")
    op.drop_table("agent_memories")
    op.drop_column("agents", "memory_enabled")
