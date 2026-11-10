"""Agent control plane: users, sessions, keys, agents/versions, runs/events.

Revision ID: 002_agent_control_plane
Revises: 001_health_checks
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision: str = "002_agent_control_plane"
down_revision: str | None = "001_health_checks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEMO_AGENT_ID = "00000000-0000-4000-8000-000000000001"
DEMO_VERSION_ID = "00000000-0000-4000-8000-000000000002"
DEMO_PROMPT = (
    "You are demo-chat, a concise assistant for the ai-agents agent runtime. "
    "Use the get_server_time tool whenever the user asks about the current time or date."
)


def upgrade() -> None:
    op.create_table(
        "user_identities",
        sa.Column("sub", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("is_superadmin", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("sub"),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_sub", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_sub"], ["user_identities.sub"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_sessions_user_sub", "auth_sessions", ["user_sub"])
    op.create_table(
        "service_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("plugin_name", sa.String(length=100), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("tools", sa.JSON(), nullable=False),
        sa.Column("llm", sa.JSON(), nullable=False),
        sa.Column("limits", sa.JSON(), nullable=False),
        sa.Column("owner_kind", sa.String(length=16), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("published_version_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_agents_owner_id", "agents", ["owner_id"])
    op.create_index("ix_agents_visibility_status", "agents", ["visibility", "status"])
    op.create_table(
        "agent_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "version", name="uq_agent_versions"),
    )
    op.create_index("ix_agent_versions_agent_id", "agent_versions", ["agent_id"])
    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("agent_version_id", sa.String(length=36), nullable=True),
        sa.Column("agent_slug", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("principal_kind", sa.String(length=16), nullable=False),
        sa.Column("principal_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["agent_version_id"], ["agent_versions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runs_created_at", "runs", ["created_at"])
    op.create_index("ix_runs_principal", "runs", ["principal_kind", "principal_id"])
    op.create_index("ix_runs_agent_id", "runs", ["agent_id"])
    op.create_table(
        "run_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "seq", name="uq_run_events_seq"),
    )
    op.create_index("ix_run_events_run_id", "run_events", ["run_id"])

    now = datetime.now(timezone.utc)
    op.bulk_insert(
        sa.table(
            "user_identities",
            sa.column("sub", sa.String),
            sa.column("email", sa.String),
            sa.column("display_name", sa.String),
            sa.column("roles", sa.JSON),
            sa.column("is_superadmin", sa.Boolean),
            sa.column("created_at", sa.DateTime(timezone=True)),
        ),
        [
            {
                "sub": "system",
                "email": "system@local",
                "display_name": "system",
                "roles": [],
                "is_superadmin": False,
                "created_at": now,
            }
        ],
    )
    op.bulk_insert(
        sa.table(
            "agents",
            sa.column("id", sa.String),
            sa.column("slug", sa.String),
            sa.column("name", sa.String),
            sa.column("description", sa.Text),
            sa.column("kind", sa.String),
            sa.column("plugin_name", sa.String),
            sa.column("system_prompt", sa.Text),
            sa.column("tools", sa.JSON),
            sa.column("llm", sa.JSON),
            sa.column("limits", sa.JSON),
            sa.column("owner_kind", sa.String),
            sa.column("owner_id", sa.String),
            sa.column("tenant_id", sa.String),
            sa.column("visibility", sa.String),
            sa.column("status", sa.String),
            sa.column("published_version_id", sa.String),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        ),
        [
            {
                "id": DEMO_AGENT_ID,
                "slug": "demo-chat",
                "name": "Demo Chat",
                "description": "Demo agent with the get_server_time tool",
                "kind": "preset",
                "plugin_name": None,
                "system_prompt": DEMO_PROMPT,
                "tools": ["get_server_time"],
                "llm": {"base_url": None, "model": None, "temperature": 0.2},
                "limits": {"max_steps": 8, "timeout_seconds": 120},
                "owner_kind": "system",
                "owner_id": "system",
                "tenant_id": "default",
                "visibility": "shared",
                "status": "published",
                "published_version_id": DEMO_VERSION_ID,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    op.bulk_insert(
        sa.table(
            "agent_versions",
            sa.column("id", sa.String),
            sa.column("agent_id", sa.String),
            sa.column("version", sa.Integer),
            sa.column("snapshot", sa.JSON),
            sa.column("created_by", sa.String),
            sa.column("created_at", sa.DateTime(timezone=True)),
        ),
        [
            {
                "id": DEMO_VERSION_ID,
                "agent_id": DEMO_AGENT_ID,
                "version": 1,
                "snapshot": {
                    "name": "Demo Chat",
                    "description": "Demo agent with the get_server_time tool",
                    "kind": "preset",
                    "plugin_name": None,
                    "system_prompt": DEMO_PROMPT,
                    "tools": ["get_server_time"],
                    "llm": {"base_url": None, "model": None, "temperature": 0.2},
                    "limits": {"max_steps": 8, "timeout_seconds": 120},
                },
                "created_by": "system",
                "created_at": now,
            }
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_run_events_run_id", table_name="run_events")
    op.drop_table("run_events")
    op.drop_index("ix_runs_agent_id", table_name="runs")
    op.drop_index("ix_runs_principal", table_name="runs")
    op.drop_index("ix_runs_created_at", table_name="runs")
    op.drop_table("runs")
    op.drop_index("ix_agent_versions_agent_id", table_name="agent_versions")
    op.drop_table("agent_versions")
    op.drop_index("ix_agents_visibility_status", table_name="agents")
    op.drop_index("ix_agents_owner_id", table_name="agents")
    op.drop_table("agents")
    op.drop_table("service_keys")
    op.drop_index("ix_auth_sessions_user_sub", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("user_identities")
