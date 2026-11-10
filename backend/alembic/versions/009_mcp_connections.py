"""MCP connections: external MCP servers whose tools agents can call.

Revision ID: 009_mcp_connections
Revises: 008_mcp_servers
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009_mcp_connections"
down_revision: str | None = "008_mcp_servers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("headers", sa.JSON(), nullable=False),
        sa.Column("tools_cache", sa.JSON(), nullable=False),
        sa.Column("tools_cached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("30")
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "owner_kind", sa.String(length=16), nullable=False, server_default="user"
        ),
        sa.Column("owner_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )


def downgrade() -> None:
    op.drop_table("mcp_connections")
