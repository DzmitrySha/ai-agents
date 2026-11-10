"""Code-registered plugin packs: provenance + install marker.

Revision ID: 022_plugin_packs
Revises: 021_agent_memory
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "022_plugin_packs"
down_revision: str | None = "021_agent_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("pack_name", sa.String(length=64), nullable=True))
    op.add_column("agents", sa.Column("pack_version", sa.String(length=32), nullable=True))
    op.create_table(
        "pack_installs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("installed_by", sa.String(length=64), nullable=False),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", "version", name="uq_pack_installs_name_version"),
    )
    op.create_index("ix_pack_installs_name", "pack_installs", ["name"])


def downgrade() -> None:
    op.drop_index("ix_pack_installs_name", table_name="pack_installs")
    op.drop_table("pack_installs")
    op.drop_column("agents", "pack_version")
    op.drop_column("agents", "pack_name")
