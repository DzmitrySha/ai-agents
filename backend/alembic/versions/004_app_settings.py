"""Project-wide LLM settings (single row).

Revision ID: 004_app_settings
Revises: 003_tools_skills
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004_app_settings"
down_revision: str | None = "003_tools_skills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("llm_base_url", sa.String(length=500), nullable=True),
        sa.Column("llm_model", sa.String(length=200), nullable=True),
        sa.Column("llm_api_key", sa.String(length=500), nullable=True),
        sa.Column("updated_by", sa.String(length=200), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
