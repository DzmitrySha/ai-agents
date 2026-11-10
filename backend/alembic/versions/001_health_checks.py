"""empty alembic script template."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "001_health_checks"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "health_checks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("note", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("health_checks")
