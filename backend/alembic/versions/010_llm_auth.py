"""LLM provider auth scheme: header name and token prefix are configurable.

Revision ID: 010_llm_auth
Revises: 009_mcp_connections
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "010_llm_auth"
down_revision: str | None = "009_mcp_connections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "llm_providers",
        sa.Column(
            "auth_type", sa.String(length=16), nullable=False, server_default="bearer"
        ),
    )
    op.add_column(
        "llm_providers",
        sa.Column(
            "auth_header",
            sa.String(length=64),
            nullable=False,
            server_default="Authorization",
        ),
    )
    op.add_column(
        "llm_providers",
        sa.Column(
            "auth_prefix", sa.String(length=32), nullable=False, server_default="Bearer "
        ),
    )


def downgrade() -> None:
    op.drop_column("llm_providers", "auth_prefix")
    op.drop_column("llm_providers", "auth_header")
    op.drop_column("llm_providers", "auth_type")
