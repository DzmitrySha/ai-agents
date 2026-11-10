"""Pydantic contracts for agents, runs, events, keys."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.settings import get_settings

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
# `mcp:<connection-slug>:<tool>` — инструмент внешнего MCP-сервера.
MCP_REF_RE = re.compile(r"^mcp:([a-z0-9][a-z0-9-]{1,62}):([A-Za-z0-9_.-]{1,128})$")
ALLOWED_LLM_KEYS = {"base_url", "model", "temperature"}
ALLOWED_LIMIT_KEYS = {
    "max_steps",
    "timeout_seconds",
    "max_tokens",
    "max_attempts",
    "approval_mode",
}
# Access to API surfaces. Prefer *:execute over *:write for "run an action".
# Legacy `runs:write` is rewritten to `runs:execute` on load / migration.
SCOPES = [
    "agents:read",
    "agents:write",
    "tools:read",
    "tools:execute",
    "tools:write",
    "skills:read",
    "skills:write",
    "runs:read",
    "runs:execute",
    "admin",
]
SCOPE_ALIASES = {"runs:write": "runs:execute"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunStatus(str, Enum):
    queued = "queued"
    running = "running"
    waiting_approval = "waiting_approval"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


TERMINAL_STATUSES: frozenset[str] = frozenset(
    {RunStatus.succeeded.value, RunStatus.failed.value, RunStatus.cancelled.value}
)


class FailureKind(str, Enum):
    transient = "transient"
    rate_limit = "rate_limit"
    timeout = "timeout"
    token_budget = "token_budget"
    step_limit = "step_limit"
    tool = "tool"
    approval_rejected = "approval_rejected"
    internal = "internal"
    cancelled = "cancelled"


AUTH_TYPES = ("bearer", "header", "none")
HEADER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}$")


class LLMConfig(BaseModel):
    """LLM settings. `api_key` is accepted per run only, never persisted.

    `auth_type`/`auth_header`/`auth_prefix` describe how the token is sent:
    `bearer` → `<auth_header>: <prefix><key>` (prefix defaults to "Bearer "),
    `header` → the same without a default prefix, `none` → no auth header.
    """

    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    auth_type: Literal["bearer", "header", "none"] | None = None
    auth_header: str | None = None
    auth_prefix: str | None = None


class CreateRunRequest(BaseModel):
    agent_id: str = Field(min_length=1)
    input: str | dict[str, Any] | list[Any]
    llm: LLMConfig | None = None
    metadata: dict[str, Any] | None = None


class RunEvent(BaseModel):
    seq: int
    event: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utcnow)


class Run(BaseModel):
    run_id: str
    agent_id: str
    status: RunStatus
    input: str | dict[str, Any] | list[Any]
    metadata: dict[str, Any] | None = None
    output: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RunOut(Run):
    agent_version: int | None = None
    harness_hash: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    failure_kind: str | None = None
    attempts: int | None = None
    parent_run_id: str | None = None
    depth: int = 0
    events_archived_at: datetime | None = None


class RunHarness(BaseModel):
    run_id: str
    harness_hash: str | None = None
    snapshot: dict[str, Any] | None = None


class ToolCallDigest(BaseModel):
    tool: str
    calls: int
    errors: int


class TrajectoryDigest(BaseModel):
    run_id: str
    agent_id: str
    agent_version: int | None = None
    harness_hash: str | None = None
    status: RunStatus
    duration_ms: int | None = None
    steps: int = 0
    events_total: int = 0
    tool_calls: list[ToolCallDigest] = Field(default_factory=list)
    total_tool_calls: int = 0
    failed_tool_calls: int = 0
    unfinished_tool_calls: int = 0
    output_chars: int = 0
    error: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    failure_kind: str | None = None
    attempts: int | None = None


class PreflightRequest(BaseModel):
    agent_id: str = Field(min_length=1)
    llm: LLMConfig | None = None


class RunApprovalOut(BaseModel):
    id: str
    run_id: str
    tool: str
    input: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "approved", "rejected", "expired"]
    requested_at: datetime
    resolved_at: datetime | None = None
    resolved_by: str = ""


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "reject"]


class DoctorCheck(BaseModel):
    id: str
    status: Literal["ok", "warn", "error", "skip"]
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = 0


class DoctorResult(BaseModel):
    ok: bool
    generated_at: datetime = Field(default_factory=utcnow)
    checks: list[DoctorCheck] = Field(default_factory=list)


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    agent_slug: str = Field(min_length=1, max_length=64)
    input: str | dict[str, Any] | list[Any]
    cron: str = Field(min_length=1, max_length=64)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    agent_slug: str | None = Field(default=None, min_length=1, max_length=64)
    input: str | dict[str, Any] | list[Any] | None = None
    cron: str | None = Field(default=None, min_length=1, max_length=64)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    enabled: bool | None = None


class ScheduleOut(BaseModel):
    id: str
    name: str
    agent_slug: str
    input: str | dict[str, Any] | list[Any]
    cron: str
    timezone: str
    enabled: bool
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_run_id: str | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class ScheduleList(BaseModel):
    items: list[ScheduleOut] = Field(default_factory=list)
    total: int = 0


class NotificationChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["webhook", "telegram"]
    url: str | None = None
    secret: str | None = None
    chat_id: str | None = None
    enabled: bool = True


class NotificationChannelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = None
    secret: str | None = None
    chat_id: str | None = None
    enabled: bool | None = None


class NotificationChannelOut(BaseModel):
    id: str
    name: str
    kind: Literal["webhook", "telegram"]
    url: str | None = None
    chat_id: str | None = None
    enabled: bool
    secret_configured: bool = False
    created_at: datetime
    updated_at: datetime


class DeliveryOut(BaseModel):
    id: str
    run_id: str
    channel_id: str
    status: Literal["pending", "sent", "failed"]
    attempts: int
    next_attempt_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    sent_at: datetime | None = None


class DeliveryList(BaseModel):
    items: list[DeliveryOut] = Field(default_factory=list)
    total: int = 0


class AgentMemoryOut(BaseModel):
    id: str
    agent_id: str
    namespace: str
    key: str
    content: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None


class PackChange(BaseModel):
    entity: Literal["agent"] = "agent"
    ref: str
    action: Literal["create", "update", "noop"]


class PackInstallResult(BaseModel):
    name: str
    version: str
    dry_run: bool = False
    installed: bool = False
    already_installed: bool = False
    changes: list[PackChange] = Field(default_factory=list)


class PackOut(BaseModel):
    name: str
    version: str
    description: str = ""
    source: Literal["code", "custom"] = "code"
    agents: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    installed_versions: list[str] = Field(default_factory=list)


class PreflightCheck(BaseModel):
    id: Literal["agent", "plugin", "quota", "tools", "skills", "mcp", "llm", "limits"]
    status: Literal["ok", "warn", "error", "skip"]
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class PreflightEffective(BaseModel):
    agent_id: str
    agent_version: int | None = None
    model: str | None = None
    base_url: str | None = None
    max_steps: int
    timeout_seconds: float
    max_tokens: int
    max_attempts: int
    approval_mode: str
    sub_agents: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    mcp: list[str] = Field(default_factory=list)


class PreflightResult(BaseModel):
    ok: bool
    checks: list[PreflightCheck] = Field(default_factory=list)
    effective: PreflightEffective


class HarnessDiffItem(BaseModel):
    field: str
    left: Any = None
    right: Any = None
    changed: bool


class RunCompareResult(BaseModel):
    left: RunOut
    right: RunOut
    left_digest: TrajectoryDigest
    right_digest: TrajectoryDigest
    diff: list[HarnessDiffItem] = Field(default_factory=list)


class RunList(BaseModel):
    items: list[RunOut] = Field(default_factory=list)
    total: int = 0


class AgentUpsert(BaseModel):
    slug: str
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    kind: Literal["preset", "plugin"] = "preset"
    plugin_name: str | None = None
    system_prompt: str = ""
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    sub_agents: list[str] = Field(default_factory=list)
    memory_enabled: bool = False
    llm: dict[str, Any] = Field(default_factory=dict)
    limits: dict[str, Any] = Field(default_factory=dict)

    @field_validator("slug")
    @classmethod
    def _slug(cls, value: str) -> str:
        if not SLUG_RE.match(value):
            raise ValueError("slug must match ^[a-z0-9][a-z0-9-]{1,62}$")
        return value

    @field_validator("tools")
    @classmethod
    def _tool_refs(cls, value: list[str]) -> list[str]:
        # Builtin/custom/MCP tools are resolved against the registry in repos
        # (DB-aware); here we only enforce the ref shape and de-duplicate.
        cleaned: list[str] = []
        for name in value:
            if not (SLUG_RE.match(name) or MCP_REF_RE.match(name)):
                raise ValueError(f"invalid tool name: {name!r}")
            if name not in cleaned:
                cleaned.append(name)
        return cleaned

    @field_validator("skills")
    @classmethod
    def _skill_refs(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for name in value:
            if not SLUG_RE.match(name):
                raise ValueError(f"invalid skill name: {name!r}")
            if name not in cleaned:
                cleaned.append(name)
        return cleaned

    @field_validator("sub_agents")
    @classmethod
    def _sub_agent_refs(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for name in value:
            if not SLUG_RE.match(name):
                raise ValueError(f"invalid sub-agent slug: {name!r}")
            if name not in cleaned:
                cleaned.append(name)
        return cleaned

    @field_validator("llm")
    @classmethod
    def _llm(cls, value: dict[str, Any]) -> dict[str, Any]:
        extra = set(value) - ALLOWED_LLM_KEYS
        if extra:
            raise ValueError(
                "llm allows only base_url/model/temperature; got " + ", ".join(sorted(extra))
            )
        return value

    @field_validator("limits")
    @classmethod
    def _limits(cls, value: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        extra = set(value) - ALLOWED_LIMIT_KEYS
        if extra:
            raise ValueError(
                "limits allows only max_steps/timeout_seconds/max_tokens; got "
                + ", ".join(sorted(extra))
            )
        if "max_steps" in value:
            steps = value["max_steps"]
            if not isinstance(steps, int) or isinstance(steps, bool) or not 1 <= steps <= settings.max_steps_cap:
                raise ValueError(f"limits.max_steps must be 1..{settings.max_steps_cap}")
        if "timeout_seconds" in value:
            timeout = value["timeout_seconds"]
            if (
                not isinstance(timeout, (int, float))
                or isinstance(timeout, bool)
                or not 1 <= timeout <= settings.run_timeout_cap_seconds
            ):
                raise ValueError(
                    f"limits.timeout_seconds must be 1..{settings.run_timeout_cap_seconds:g}"
                )
        if "max_tokens" in value:
            tokens = value["max_tokens"]
            if (
                not isinstance(tokens, int)
                or isinstance(tokens, bool)
                or not 1 <= tokens <= settings.run_token_cap
            ):
                raise ValueError(
                    f"limits.max_tokens must be 1..{settings.run_token_cap}"
                )
        if "max_attempts" in value:
            attempts = value["max_attempts"]
            if (
                not isinstance(attempts, int)
                or isinstance(attempts, bool)
                or not 1 <= attempts <= settings.run_max_attempts_cap
            ):
                raise ValueError(
                    f"limits.max_attempts must be 1..{settings.run_max_attempts_cap}"
                )
        if "approval_mode" in value:
            mode = value["approval_mode"]
            if mode not in {"never", "mutating", "all"}:
                raise ValueError("limits.approval_mode must be never/mutating/all")
        return value

    @model_validator(mode="after")
    def _kind_rules(self) -> AgentUpsert:
        if self.kind == "plugin":
            if not (self.plugin_name or "").strip():
                raise ValueError("plugin_name is required when kind=plugin")
        else:
            if self.plugin_name:
                raise ValueError("plugin_name is not allowed when kind=preset")
            if not self.system_prompt.strip():
                raise ValueError("system_prompt is required when kind=preset")
        return self


class PackManifest(BaseModel):
    """A code-registered bundle of agents plus existing skill/tool refs."""

    name: str
    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,31}$")
    description: str = ""
    agents: list[AgentUpsert] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not SLUG_RE.match(value):
            raise ValueError("slug must match ^[a-z0-9][a-z0-9-]{1,62}$")
        return value

    @field_validator("skills")
    @classmethod
    def _skills(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for name in value:
            if not SLUG_RE.match(name):
                raise ValueError(f"invalid skill name: {name!r}")
            if name not in cleaned:
                cleaned.append(name)
        return cleaned

    @field_validator("tools")
    @classmethod
    def _tools(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for name in value:
            if not (SLUG_RE.match(name) or MCP_REF_RE.match(name)):
                raise ValueError(f"invalid tool name: {name!r}")
            if name not in cleaned:
                cleaned.append(name)
        return cleaned

    @model_validator(mode="after")
    def _unique_agents(self) -> "PackManifest":
        seen: set[str] = set()
        for agent in self.agents:
            if agent.slug in seen:
                raise ValueError(f"duplicate agent slug: {agent.slug!r}")
            seen.add(agent.slug)
            if agent.kind != "preset":
                raise ValueError("packs may define only preset agents")
            if agent.plugin_name:
                raise ValueError("packs may not define plugin_name")
        return self


class AgentUpdate(BaseModel):
    slug: str | None = None
    name: str | None = None
    description: str | None = None
    kind: Literal["preset", "plugin"] | None = None
    plugin_name: str | None = None
    system_prompt: str | None = None
    tools: list[str] | None = None
    skills: list[str] | None = None
    sub_agents: list[str] | None = None
    memory_enabled: bool | None = None
    llm: dict[str, Any] | None = None
    limits: dict[str, Any] | None = None


class PublishRequest(BaseModel):
    visibility: Literal["private", "shared"] = "private"


class RollbackRequest(BaseModel):
    """Publish a new version from the snapshot of an existing one."""

    version: int = Field(ge=1)
    visibility: Literal["private", "shared"] | None = None


class AgentOwner(BaseModel):
    kind: str
    id: str
    email: str | None = None


class AgentOut(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    kind: str
    plugin_name: str | None
    system_prompt: str
    tools: list[str]
    skills: list[str] = Field(default_factory=list)
    sub_agents: list[str] = Field(default_factory=list)
    memory_enabled: bool = False
    llm: dict[str, Any]
    limits: dict[str, Any]
    visibility: str
    status: str
    published_version: int | None = None
    # Live bodies vs last published snapshot (informational; runs already use live defs).
    skills_stale: bool = False
    tools_stale: bool = False
    owner: AgentOwner
    created_at: datetime
    updated_at: datetime


class AgentList(BaseModel):
    items: list[AgentOut] = Field(default_factory=list)
    total: int = 0


class AgentVersionInfo(BaseModel):
    id: str
    version: int
    created_by: str
    created_at: datetime
    snapshot: dict[str, Any]


class ToolParam(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]{0,40}$")
    type: Literal["string", "number", "integer", "boolean"] = "string"
    description: str = ""
    required: bool = True
    enum: list[str] | None = None


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    source: Literal["builtin", "custom"] = "builtin"


class ToolCreate(BaseModel):
    slug: str
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    url: str = Field(min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, str] = Field(default_factory=dict)
    body_template: str | None = None
    content_type: str = "application/json"
    parameters: list[ToolParam] = Field(default_factory=list)
    timeout_seconds: int = Field(default=20, ge=1, le=60)
    enabled: bool = True

    @field_validator("slug")
    @classmethod
    def _slug(cls, value: str) -> str:
        if not SLUG_RE.match(value):
            raise ValueError("slug must match ^[a-z0-9][a-z0-9-]{1,62}$")
        return value

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return value

    @field_validator("parameters")
    @classmethod
    def _params(cls, value: list[ToolParam]) -> list[ToolParam]:
        names = [param.name for param in value]
        if len(names) != len(set(names)):
            raise ValueError("parameter names must be unique")
        return value


class ToolUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    query: dict[str, str] | None = None
    body_template: str | None = None
    content_type: str | None = None
    parameters: list[ToolParam] | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)
    enabled: bool | None = None


class ToolTestRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


class ToolTestResult(BaseModel):
    ok: bool
    status: int | None = None
    output: str


class ToolInvokeRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


class ToolInvokeResult(BaseModel):
    ok: bool
    output: str


class CatalogAgentItem(BaseModel):
    slug: str
    name: str
    description: str = ""


class CatalogSkillItem(BaseModel):
    slug: str
    name: str
    description: str = ""


class CatalogOut(BaseModel):
    agents: list[CatalogAgentItem] = Field(default_factory=list)
    tools: list[ToolSpec] = Field(default_factory=list)
    skills: list[CatalogSkillItem] = Field(default_factory=list)


class AssistAgentRequest(BaseModel):
    """Free-form description of an agent; the LLM fills the editor form."""

    description: str = Field(min_length=3, max_length=4000)
    llm: LLMConfig | None = None


class SuggestedTool(BaseModel):
    slug: str
    name: str
    description: str = ""
    note: str = ""


class AgentSuggestion(BaseModel):
    name: str = ""
    slug: str = ""
    description: str = ""
    system_prompt: str = ""
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    new_tools: list[SuggestedTool] = Field(default_factory=list)
    notes: str = ""
    warnings: list[str] = Field(default_factory=list)


class AssistChatMessage(BaseModel):
    role: Literal["user", "assistant"] = "user"
    content: str = Field(min_length=1, max_length=8000)


class AssistChatRequest(BaseModel):
    """Чат-ассистент: вопрос по сервису + текущие значения формы."""

    mode: Literal["form", "advice", "review", "test"] = "advice"
    target: Literal[
        "agent",
        "tool",
        "llm",
        "mcp-connection",
        "mcp-server",
        "skill",
        "user",
        "service-keys",
        "general",
    ] = "general"
    message: str = Field(min_length=1, max_length=4000)
    current: dict[str, Any] = Field(default_factory=dict)
    history: list[AssistChatMessage] = Field(default_factory=list, max_length=20)
    llm: LLMConfig | None = None


class AssistChatResponse(BaseModel):
    answer: str
    fields: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


class AssistToolRequest(BaseModel):
    description: str = Field(min_length=3, max_length=4000)
    llm: LLMConfig | None = None


class ToolSuggestion(BaseModel):
    slug: str = ""
    name: str = ""
    description: str = ""
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, str] = Field(default_factory=dict)
    body_template: str | None = None
    content_type: str = "application/json"
    parameters: list[ToolParam] = Field(default_factory=list)
    notes: str = ""
    warnings: list[str] = Field(default_factory=list)


class LLMSettingsOut(BaseModel):
    """Effective project LLM endpoint. The API key itself is never returned."""

    base_url: str
    model: str
    api_key_set: bool
    api_key_hint: str | None = None
    source: Literal["db", "env", "provider"] = "env"
    auth_type: Literal["bearer", "header", "none"] = "bearer"
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer "
    updated_by: str | None = None
    updated_at: datetime | None = None


class LLMSettingsUpdate(BaseModel):
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=200)
    api_key: str | None = Field(default=None, max_length=500)
    clear_api_key: bool = False

    @field_validator("base_url")
    @classmethod
    def _base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        if not stripped.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return stripped

    @field_validator("model")
    @classmethod
    def _model(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class LLMProviderOut(BaseModel):
    id: str
    name: str
    base_url: str
    model: str
    api_key_set: bool = False
    api_key_hint: str | None = None
    auth_type: Literal["bearer", "header", "none"] = "bearer"
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer "
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LLMProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(default="", max_length=200)
    api_key: str | None = Field(default=None, max_length=500)
    auth_type: Literal["bearer", "header", "none"] = "bearer"
    auth_header: str = Field(default="Authorization", max_length=64)
    auth_prefix: str = Field(default="Bearer ", max_length=32)

    @field_validator("auth_header")
    @classmethod
    def _auth_header(cls, value: str) -> str:
        name = value.strip() or "Authorization"
        if not HEADER_NAME_RE.match(name):
            raise ValueError("auth_header must be a valid HTTP header name")
        return name

    @field_validator("auth_prefix")
    @classmethod
    def _auth_prefix(cls, value: str) -> str:
        return value or ""

    @field_validator("base_url")
    @classmethod
    def _base_url(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return stripped


class LLMProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=200)
    api_key: str | None = Field(default=None, max_length=500)
    auth_type: Literal["bearer", "header", "none"] | None = None
    auth_header: str | None = Field(default=None, max_length=64)
    auth_prefix: str | None = Field(default=None, max_length=32)
    clear_api_key: bool = False

    @field_validator("auth_header")
    @classmethod
    def _auth_header(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = value.strip()
        if not HEADER_NAME_RE.match(name):
            raise ValueError("auth_header must be a valid HTTP header name")
        return name

    @field_validator("base_url")
    @classmethod
    def _base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return stripped


class LLMProvidersOut(BaseModel):
    items: list[LLMProviderOut] = Field(default_factory=list)
    active_id: str | None = None
    effective: LLMSettingsOut


class LLMProviderDeleted(BaseModel):
    deleted: bool = True
    active_id: str | None = None


class ActiveProviderRequest(BaseModel):
    provider_id: str | None = None


class LLMModelsRequest(BaseModel):
    """Probe a provider for its models; empty fields fall back to saved settings."""

    base_url: str | None = None
    api_key: str | None = None
    auth_type: Literal["bearer", "header", "none"] | None = None
    auth_header: str | None = None
    auth_prefix: str | None = None


class LLMModelsOut(BaseModel):
    base_url: str
    models: list[str] = Field(default_factory=list)


class ToolOut(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    kind: str
    method: str
    url: str
    header_names: list[str] = Field(default_factory=list)
    query: dict[str, str]
    body_template: str | None
    content_type: str
    parameters: list[ToolParam]
    timeout_seconds: int
    enabled: bool
    owner: AgentOwner
    created_at: datetime
    updated_at: datetime


class ToolList(BaseModel):
    items: list[ToolOut] = Field(default_factory=list)
    total: int = 0


class ToolUserAgent(BaseModel):
    slug: str
    name: str
    status: str
    published_version: int | None = None


class ToolUsageOut(BaseModel):
    """Which agents reference the tool (for the delete warning)."""

    slug: str
    total: int = 0
    agents: list[ToolUserAgent] = Field(default_factory=list)


class ToolDeleteResult(BaseModel):
    slug: str
    detached_agents: list[str] = Field(default_factory=list)


class SkillOut(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    source: str
    source_id: str | None
    source_url: str | None
    hash: str | None
    created_at: datetime
    updated_at: datetime


class SkillDetail(SkillOut):
    content: str
    files: list[dict[str, Any]] = Field(default_factory=list)


class SkillList(BaseModel):
    items: list[SkillOut] = Field(default_factory=list)
    total: int = 0


class SkillImportRequest(BaseModel):
    url: str = Field(min_length=3)


class SkillLocalFile(BaseModel):
    """Один файл навыка при загрузке из браузера (путь относительный, для slug/файлов)."""

    path: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=40000)


class SkillLocalImportRequest(BaseModel):
    """Импорт с диска API или из браузера: либо `path`, либо `entries`."""

    path: str | None = Field(default=None, max_length=1000)
    entries: list[SkillLocalFile] | None = Field(default=None, max_length=100)


class SkillLocalImportSkipped(BaseModel):
    path: str
    reason: str


class SkillLocalImportResult(BaseModel):
    items: list[SkillOut] = Field(default_factory=list)
    created: int = 0
    updated: int = 0
    skipped: list[SkillLocalImportSkipped] = Field(default_factory=list)


class SkillCreate(BaseModel):
    """Свой навык по шаблону skills.sh (SKILL.md)."""

    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=64)
    description: str = Field(default="", max_length=4000)
    content: str = Field(default="", max_length=40000)


class SkillUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    content: str | None = Field(default=None, max_length=40000)


class AssistSkillRequest(BaseModel):
    description: str = Field(min_length=3, max_length=4000)
    llm: LLMConfig | None = None


class SkillSuggestion(BaseModel):
    name: str = ""
    slug: str = ""
    description: str = ""
    content: str = ""
    notes: str = ""
    warnings: list[str] = Field(default_factory=list)


class IdentityUser(BaseModel):
    """Запись из каталога Keycloak (Keycloak)."""

    sub: str
    username: str = ""
    email: str | None = None
    display_name: str | None = None
    enabled: bool = True


class IdentityUserPage(BaseModel):
    items: list[IdentityUser] = Field(default_factory=list)
    has_more: bool = False


class AdminUserOut(BaseModel):
    id: str
    email: str | None = None
    display_name: str | None = None
    roles: list[str] = Field(default_factory=list)
    is_superadmin: bool = False
    # SUPERADMIN_EMAILS: понизить нельзя, назначает только такой аккаунт.
    is_bootstrap: bool = False
    app_role: Literal["superadmin", "admin", "user"] = "user"
    daily_run_limit: int | None = None
    runs_today: int = 0
    last_login_at: datetime | None = None


class AdminUserCreate(BaseModel):
    sub: str = Field(min_length=1, max_length=64)
    email: str | None = Field(default=None, max_length=320)
    display_name: str | None = Field(default=None, max_length=200)
    app_role: Literal["superadmin", "admin", "user"] = "user"
    daily_run_limit: int | None = Field(default=None, ge=0, le=100000)


class AdminUserUpdate(BaseModel):
    app_role: Literal["superadmin", "admin", "user"] | None = None
    daily_run_limit: int | None = Field(default=None, ge=0, le=100000)


class ServiceKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[str] = Field(min_length=1)
    agent_slugs: list[str] = Field(default_factory=list)
    tool_slugs: list[str] = Field(default_factory=list)
    skill_slugs: list[str] = Field(default_factory=list)

    @field_validator("scopes")
    @classmethod
    def _scopes(cls, value: list[str]) -> list[str]:
        mapped = [SCOPE_ALIASES.get(scope, scope) for scope in value]
        unknown = [scope for scope in mapped if scope not in SCOPES]
        if unknown:
            raise ValueError(f"unknown scopes: {', '.join(sorted(set(unknown)))}")
        return sorted(set(mapped))


class ServiceKeyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    scopes: list[str] | None = None
    enabled: bool | None = None
    agent_slugs: list[str] | None = None
    tool_slugs: list[str] | None = None
    skill_slugs: list[str] | None = None

    @field_validator("scopes")
    @classmethod
    def _scopes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        mapped = [SCOPE_ALIASES.get(scope, scope) for scope in value]
        unknown = [scope for scope in mapped if scope not in SCOPES]
        if unknown:
            raise ValueError(f"unknown scopes: {', '.join(sorted(set(unknown)))}")
        return sorted(set(mapped))


class ServiceKeyOut(BaseModel):
    id: str
    name: str
    scopes: list[str]
    agent_slugs: list[str] = Field(default_factory=list)
    tool_slugs: list[str] = Field(default_factory=list)
    skill_slugs: list[str] = Field(default_factory=list)
    enabled: bool
    created_at: datetime
    last_used_at: datetime | None = None


class ServiceKeyCreated(ServiceKeyOut):
    key: str


class McpServerOut(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    enabled: bool
    agent_slugs: list[str] = Field(default_factory=list)
    tool_slugs: list[str] = Field(default_factory=list)
    skill_slugs: list[str] = Field(default_factory=list)
    created_by: str
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None
    url: str


class McpServerCreated(McpServerOut):
    api_key: str


class McpServerList(BaseModel):
    items: list[McpServerOut] = Field(default_factory=list)
    total: int = 0


class McpServerCreate(BaseModel):
    slug: str
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    agent_slugs: list[str] = Field(default_factory=list)
    tool_slugs: list[str] = Field(default_factory=list)
    skill_slugs: list[str] = Field(default_factory=list)

    @field_validator("slug")
    @classmethod
    def _slug(cls, value: str) -> str:
        if not SLUG_RE.match(value):
            raise ValueError("slug must match ^[a-z0-9][a-z0-9-]{1,62}$")
        return value


class McpServerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    enabled: bool | None = None
    agent_slugs: list[str] | None = None
    tool_slugs: list[str] | None = None
    skill_slugs: list[str] | None = None
    rotate_key: bool = False


class McpToolInfo(BaseModel):
    name: str
    description: str = ""


class McpConnectionCreate(BaseModel):
    slug: str
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    url: str = Field(min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    enabled: bool = True

    @field_validator("slug")
    @classmethod
    def _slug(cls, value: str) -> str:
        if not SLUG_RE.match(value):
            raise ValueError("slug must match ^[a-z0-9][a-z0-9-]{1,62}$")
        return value

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return value


class McpConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=120)
    enabled: bool | None = None


class McpConnectionOut(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    url: str
    header_names: list[str] = Field(default_factory=list)
    timeout_seconds: int
    enabled: bool
    owner: AgentOwner
    tools_cache: list[McpToolInfo] = Field(default_factory=list)
    tools_cached_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class McpConnectionList(BaseModel):
    items: list[McpConnectionOut] = Field(default_factory=list)
    total: int = 0


class McpConnectionTestResult(BaseModel):
    ok: bool
    tools: list[McpToolInfo] = Field(default_factory=list)
    error: str | None = None


class McpConnectionDeleteResult(BaseModel):
    slug: str
    detached_agents: list[str] = Field(default_factory=list)


class RunsDailyPoint(BaseModel):
    date: str
    succeeded: int = 0
    failed: int = 0
    cancelled: int = 0
    other: int = 0


class ToolDailyPoint(BaseModel):
    date: str
    calls: int = 0


class ApiDailyPoint(BaseModel):
    date: str
    calls: int = 0
    errors: int = 0


class AgentUsage(BaseModel):
    slug: str
    runs: int = 0
    succeeded: int = 0
    failed: int = 0
    success_rate: float = 0.0
    avg_duration_ms: int | None = None
    tokens: int = 0


class ToolUsage(BaseModel):
    slug: str
    calls: int = 0


class EndpointUsage(BaseModel):
    method: str
    path: str
    calls: int = 0
    errors: int = 0
    p95_ms: int | None = None


class LatencyStats(BaseModel):
    p50_ms: int | None = None
    p95_ms: int | None = None


class StatsOverview(BaseModel):
    """Агрегаты за окно `days` (UTC), готовые для графиков."""

    days: int
    since: datetime
    runs_total: int = 0
    runs_succeeded: int = 0
    success_rate: float = 0.0
    runs_daily: list[RunsDailyPoint] = Field(default_factory=list)
    tokens_total: int = 0
    queued_runs: int = 0
    oldest_queued_seconds: int | None = None
    tools_total: int = 0
    tools_daily: list[ToolDailyPoint] = Field(default_factory=list)
    api_total: int = 0
    api_errors: int = 0
    api_latency: LatencyStats = Field(default_factory=LatencyStats)
    api_daily: list[ApiDailyPoint] = Field(default_factory=list)
    top_agents: list[AgentUsage] = Field(default_factory=list)
    top_tools: list[ToolUsage] = Field(default_factory=list)
    top_endpoints: list[EndpointUsage] = Field(default_factory=list)
