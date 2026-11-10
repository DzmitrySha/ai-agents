"""Application roles and per-user daily run limit.

Revision ID: 006_user_roles
Revises: 005_usage_events
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006_user_roles"
down_revision: str | None = "005_usage_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_identities",
        sa.Column("app_role", sa.String(length=16), nullable=False, server_default="user"),
    )
    op.add_column(
        "user_identities",
        sa.Column("daily_run_limit", sa.Integer(), nullable=True),
    )
    # Существующие суперадмины остаются суперадминами; владельцы агентов получают admin.
    op.execute("UPDATE user_identities SET app_role = 'superadmin' WHERE is_superadmin")
    op.execute(
        "UPDATE user_identities SET app_role = 'admin'"
        " WHERE is_superadmin = false"
        " AND sub IN (SELECT owner_id FROM agents WHERE owner_kind = 'user')"
    )


def downgrade() -> None:
    op.drop_column("user_identities", "daily_run_limit")
    op.drop_column("user_identities", "app_role")
