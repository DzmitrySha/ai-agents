"""MCP servers: allowlist of published shared agent slugs per key.

Revision ID: 011_mcp_server_agent_slugs
Revises: 010_llm_auth
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "011_mcp_server_agent_slugs"
down_revision: str | None = "010_llm_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mcp_servers",
        sa.Column(
            "agent_slugs",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("mcp_servers", "agent_slugs")
