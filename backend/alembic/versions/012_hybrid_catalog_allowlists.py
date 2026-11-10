"""Hybrid catalog allowlists on mcp_servers and service_keys.

Revision ID: 012_hybrid_catalog_allowlists
Revises: 011_mcp_server_agent_slugs
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "012_hybrid_catalog_allowlists"
down_revision: str | None = "011_mcp_server_agent_slugs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMPTY = sa.text("'[]'")


def upgrade() -> None:
    op.add_column(
        "mcp_servers",
        sa.Column("tool_slugs", sa.JSON(), nullable=False, server_default=_EMPTY),
    )
    op.add_column(
        "mcp_servers",
        sa.Column("skill_slugs", sa.JSON(), nullable=False, server_default=_EMPTY),
    )
    op.add_column(
        "service_keys",
        sa.Column("agent_slugs", sa.JSON(), nullable=False, server_default=_EMPTY),
    )
    op.add_column(
        "service_keys",
        sa.Column("tool_slugs", sa.JSON(), nullable=False, server_default=_EMPTY),
    )
    op.add_column(
        "service_keys",
        sa.Column("skill_slugs", sa.JSON(), nullable=False, server_default=_EMPTY),
    )


def downgrade() -> None:
    op.drop_column("service_keys", "skill_slugs")
    op.drop_column("service_keys", "tool_slugs")
    op.drop_column("service_keys", "agent_slugs")
    op.drop_column("mcp_servers", "skill_slugs")
    op.drop_column("mcp_servers", "tool_slugs")
