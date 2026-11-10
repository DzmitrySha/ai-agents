"""Named LLM providers + active provider pointer.

Revision ID: 007_llm_providers
Revises: 006_user_roles
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007_llm_providers"
down_revision: str | None = "006_user_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_providers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("api_key", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.add_column(
        "app_settings",
        sa.Column("active_llm_provider_id", sa.String(length=36), nullable=True),
    )

    # Существующие настройки превращаем в первого провайдера и делаем активным.
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            "SELECT llm_base_url, llm_model, llm_api_key FROM app_settings WHERE id = 'default'"
        )
    ).first()
    if row and any(row):
        provider_id = str(uuid.uuid4())
        bind.execute(
            sa.text(
                "INSERT INTO llm_providers (id, name, base_url, model, api_key, created_by)"
                " VALUES (:id, :name, :base_url, :model, :api_key, 'migration')"
            ),
            {
                "id": provider_id,
                "name": "default",
                "base_url": row[0] or "",
                "model": row[1] or "",
                "api_key": row[2],
            },
        )
        bind.execute(
            sa.text(
                "UPDATE app_settings SET active_llm_provider_id = :pid WHERE id = 'default'"
            ),
            {"pid": provider_id},
        )


def downgrade() -> None:
    op.drop_column("app_settings", "active_llm_provider_id")
    op.drop_table("llm_providers")
