"""ORM models: users, sessions, service keys, agents/versions, runs/events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class HealthCheck(Base):
    """Minimal table so Alembic has a real migration to apply."""

    __tablename__ = "health_checks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    note: Mapped[str] = mapped_column(String(200), default="ok")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UserIdentity(Base):
    __tablename__ = "user_identities"

    sub: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320), default=None)
    display_name: Mapped[str | None] = mapped_column(String(200), default=None)
    roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    # superadmin | admin | user — определяет скоупы и лимиты внутри сервиса
    app_role: Mapped[str] = mapped_column(String(16), default="user")
    # None → берётся USER_DAILY_RUN_LIMIT
    daily_run_limit: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_sub: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_identities.sub", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class ServiceKey(Base):
    __tablename__ = "service_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Catalog allowlists (fail-closed for REST catalog/invoke): empty → deny category.
    agent_slugs: Mapped[list[str]] = mapped_column(JSON, default=list)
    tool_slugs: Mapped[list[str]] = mapped_column(JSON, default=list)
    skill_slugs: Mapped[list[str]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )


class McpServer(Base):
    """Именованный ключ доступа к MCP-endpoint'у (`/mcp`)."""

    __tablename__ = "mcp_servers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # Allowlists: empty list → that category absent from tools/list.
    agent_slugs: Mapped[list[str]] = mapped_column(JSON, default=list)
    tool_slugs: Mapped[list[str]] = mapped_column(JSON, default=list)
    skill_slugs: Mapped[list[str]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )


class McpConnection(Base):
    """Внешний MCP-сервер (Streamable HTTP), tools которого доступны агентам."""

    __tablename__ = "mcp_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(Text)
    headers: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    tools_cache: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    tools_cached_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_kind: Mapped[str] = mapped_column(String(16), default="user")
    owner_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        Index("ix_agents_owner_id", "owner_id"),
        Index("ix_agents_visibility_status", "visibility", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(16), default="preset")
    plugin_name: Mapped[str | None] = mapped_column(String(100), default=None)
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    tools: Mapped[list[str]] = mapped_column(JSON, default=list)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    sub_agents: Mapped[list[str]] = mapped_column(JSON, default=list)
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    llm: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    limits: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    owner_kind: Mapped[str] = mapped_column(String(16), default="user")
    owner_id: Mapped[str] = mapped_column(String(64), default="")
    tenant_id: Mapped[str] = mapped_column(String(64), default="default")
    visibility: Mapped[str] = mapped_column(String(16), default="private")
    status: Mapped[str] = mapped_column(String(16), default="draft")
    pack_name: Mapped[str | None] = mapped_column(String(64), default=None)
    pack_version: Mapped[str | None] = mapped_column(String(32), default=None)
    published_version_id: Mapped[str | None] = mapped_column(
        String(36), default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AgentVersion(Base):
    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("agent_id", "version", name="uq_agent_versions"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PackInstall(Base):
    """One successful install of a code-registered pack version."""

    __tablename__ = "pack_installs"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_pack_installs_name_version"),
        Index("ix_pack_installs_name", "name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(32))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    installed_by: Mapped[str] = mapped_column(String(64), default="")
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CustomPack(Base):
    """Admin-imported data-only pack, editable without rebuilding the image."""

    __tablename__ = "custom_packs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class RunRow(Base):
    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_created_at", "created_at"),
        Index("ix_runs_principal", "principal_kind", "principal_id"),
        Index("ix_runs_agent_id", "agent_id"),
        Index("ix_runs_finished_at", "finished_at"),
        Index("ix_runs_failure_kind_created", "failure_kind", "created_at"),
        Index("ix_runs_parent_run_id", "parent_run_id"),
        Index(
            "uq_runs_idempotency",
            "principal_kind",
            "principal_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), default=None
    )
    agent_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_versions.id", ondelete="SET NULL"), default=None
    )
    agent_slug: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    input: Mapped[Any] = mapped_column(JSON)
    run_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, default=None
    )
    harness_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=None
    )
    harness_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    parent_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="SET NULL"), default=None
    )
    depth: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    total_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    failure_kind: Mapped[str | None] = mapped_column(String(32), default=None)
    attempts: Mapped[int | None] = mapped_column(Integer, default=None)
    digest: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), default=None)
    events_archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    output: Mapped[str | None] = mapped_column(Text, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    principal_kind: Mapped[str] = mapped_column(String(16))
    principal_id: Mapped[str] = mapped_column(String(64))
    tenant_id: Mapped[str] = mapped_column(String(64), default="default")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )


class RunEventRow(Base):
    __tablename__ = "run_events"
    __table_args__ = (UniqueConstraint("run_id", "seq", name="uq_run_events_seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    event: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RunApprovalRow(Base):
    """Pending/resolved human decision for one mutating tool call."""

    __tablename__ = "run_approvals"
    __table_args__ = (Index("ix_run_approvals_run_status", "run_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE")
    )
    tool: Mapped[str] = mapped_column(String(200))
    input: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    resolved_by: Mapped[str] = mapped_column(String(64), default="")


class AgentMemoryRow(Base):
    __tablename__ = "agent_memories"
    __table_args__ = (
        UniqueConstraint(
            "agent_id",
            "principal_kind",
            "principal_id",
            "namespace",
            "key",
            name="uq_agent_memories_scope_key",
        ),
        Index("ix_agent_memories_scope", "agent_id", "principal_kind", "principal_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE")
    )
    principal_kind: Mapped[str] = mapped_column(String(16))
    principal_id: Mapped[str] = mapped_column(String(64))
    namespace: Mapped[str] = mapped_column(String(200), default="default")
    key: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )


class RunScheduleRow(Base):
    """Cron schedule that creates runs on behalf of its creator."""

    __tablename__ = "run_schedules"
    __table_args__ = (Index("ix_run_schedules_due", "enabled", "next_run_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    agent_slug: Mapped[str] = mapped_column(String(64))
    input: Mapped[Any] = mapped_column(JSON)
    cron: Mapped[str] = mapped_column(String(64))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    principal_kind: Mapped[str] = mapped_column(String(16))
    principal_id: Mapped[str] = mapped_column(String(64))
    tenant_id: Mapped[str] = mapped_column(String(64), default="default")
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_run_id: Mapped[str | None] = mapped_column(String(36), default=None)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class NotificationChannelRow(Base):
    __tablename__ = "notification_channels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16))
    url: Mapped[str | None] = mapped_column(Text, default=None)
    secret: Mapped[str | None] = mapped_column(String(500), default=None)
    chat_id: Mapped[str | None] = mapped_column(String(100), default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DeliveryRow(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint("run_id", "channel_id", name="uq_deliveries_run_channel"),
        Index("ix_deliveries_due", "status", "next_attempt_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE")
    )
    channel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("notification_channels.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(16), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )


class CustomTool(Base):
    """No-code tool: templated HTTP request exposed as a LangChain tool."""

    __tablename__ = "custom_tools"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(16), default="http")
    method: Mapped[str] = mapped_column(String(8), default="GET")
    url: Mapped[str] = mapped_column(Text)
    headers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    query: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    body_template: Mapped[str | None] = mapped_column(Text, default=None)
    content_type: Mapped[str] = mapped_column(String(100), default="application/json")
    parameters: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=20)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_kind: Mapped[str] = mapped_column(String(16), default="user")
    owner_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Skill(Base):
    """Skill.md-style procedural knowledge imported from skills.sh or pasted manually."""

    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(32), default="manual")
    source_id: Mapped[str | None] = mapped_column(String(300), unique=True, default=None)
    source_url: Mapped[str | None] = mapped_column(String(500), default=None)
    hash: Mapped[str | None] = mapped_column(String(64), default=None)
    content: Mapped[str] = mapped_column(Text, default="")
    files: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AppSetting(Base):
    """Project-wide runtime settings (single row, id='default').

    Overrides env defaults for the OpenAI-compatible LLM endpoint used by agents
    and the autofill helpers. The API key is stored as-is and never returned.
    """

    __tablename__ = "app_settings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    llm_base_url: Mapped[str | None] = mapped_column(String(500), default=None)
    llm_model: Mapped[str | None] = mapped_column(String(200), default=None)
    llm_api_key: Mapped[str | None] = mapped_column(String(500), default=None)
    # Активный провайдер из llm_providers; NULL → legacy-поля выше → env.
    active_llm_provider_id: Mapped[str | None] = mapped_column(String(36), default=None)
    updated_by: Mapped[str] = mapped_column(String(200), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class UsageEvent(Base):
    """Fine-grained usage: tool invocations and API calls (runs live in `runs`).

    Rows are append-only; the stats endpoint aggregates them in-process so the
    same query works on PostgreSQL and SQLite (tests).
    """

    __tablename__ = "usage_events"
    __table_args__ = (
        Index("ix_usage_kind_ts", "kind", "ts"),
        Index("ix_usage_agent_ts", "agent_slug", "ts"),
        Index("ix_usage_tool_ts", "tool_slug", "ts"),
        Index("ix_usage_path_ts", "path", "ts"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    kind: Mapped[str] = mapped_column(String(16))  # tool | api
    agent_slug: Mapped[str | None] = mapped_column(String(64), default=None)
    tool_slug: Mapped[str | None] = mapped_column(String(64), default=None)
    run_id: Mapped[str | None] = mapped_column(String(36), default=None)
    principal_kind: Mapped[str] = mapped_column(String(16), default="")
    principal_id: Mapped[str] = mapped_column(String(64), default="")
    method: Mapped[str | None] = mapped_column(String(10), default=None)
    path: Mapped[str | None] = mapped_column(String(200), default=None)
    status_code: Mapped[int | None] = mapped_column(Integer, default=None)
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)


class LLMProvider(Base):
    """OpenAI-compatible провайдер (LM Studio, vLLM, внешний API…) с именем."""

    __tablename__ = "llm_providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    base_url: Mapped[str] = mapped_column(String(500))
    model: Mapped[str] = mapped_column(String(200), default="")
    api_key: Mapped[str | None] = mapped_column(String(500), default=None)
    # bearer | header | none — как отправлять токен (не все шлюзы ждут Bearer).
    auth_type: Mapped[str] = mapped_column(String(16), default="bearer")
    auth_header: Mapped[str] = mapped_column(String(64), default="Authorization")
    auth_prefix: Mapped[str] = mapped_column(String(32), default="Bearer ")
    created_by: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
