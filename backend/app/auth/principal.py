"""Authenticated caller: OIDC user (cookie) or service key (Bearer)."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.runtime.models import SCOPE_ALIASES, SCOPES


APPLICATION_ROLES = ("superadmin", "admin", "user")
# Cookie role `user`: consume catalog + execute tools/runs (no CRUD).
READER_SCOPES = frozenset(
    {
        "agents:read",
        "tools:read",
        "tools:execute",
        "skills:read",
        "runs:read",
        "runs:execute",
    }
)


def normalize_scopes(scopes: list[str] | frozenset[str] | set[str]) -> frozenset[str]:
    """Map legacy aliases and drop unknown leftovers."""
    out: set[str] = set()
    for raw in scopes:
        scope = SCOPE_ALIASES.get(str(raw), str(raw))
        if scope in SCOPES:
            out.add(scope)
    return frozenset(out)


@dataclass(frozen=True)
class Principal:
    kind: str  # "user" | "service" | "mcp"
    id: str  # Keycloak sub | service_keys.id | "env" | mcp server slug
    email: str | None = None
    is_superadmin: bool = False
    # bootstrap-суперадмин (SUPERADMIN_EMAILS): единственный, кто назначает других
    # суперадминов; остальные суперадмины управляют только admin/user.
    is_bootstrap: bool = False
    scopes: frozenset[str] = field(default_factory=frozenset)
    roles: tuple[str, ...] = ()
    tenant_id: str = "default"
    app_role: str = "user"
    daily_run_limit: int | None = None
    # DB service keys: catalog/invoke fail-closed by allowlists (empty = deny).
    # False for OIDC users and env bootstrap SERVICE_API_KEYS (unrestricted).
    catalog_restricted: bool = False
    agent_slugs: tuple[str, ...] = ()
    tool_slugs: tuple[str, ...] = ()
    skill_slugs: tuple[str, ...] = ()


def catalog_allowlist(principal: Principal, kind: str) -> set[str] | None:
    """None = unrestricted; set (possibly empty) = fail-closed allowlist."""
    if not principal.catalog_restricted:
        return None
    if kind == "agent":
        return set(principal.agent_slugs)
    if kind == "tool":
        return set(principal.tool_slugs)
    if kind == "skill":
        return set(principal.skill_slugs)
    raise ValueError(f"unknown catalog kind: {kind}")


def scopes_for_role(role: str) -> frozenset[str]:
    """superadmin — всё; admin — всё кроме управления доступами; user — чтение и запуск."""
    if role == "superadmin":
        return frozenset(SCOPES)
    if role == "admin":
        return frozenset(SCOPES) - {"admin"}
    return READER_SCOPES


def user_scopes() -> frozenset[str]:
    """Backward-compatible alias: неизвестная роль = пользователь."""
    return READER_SCOPES


def service_all_scopes() -> frozenset[str]:
    return frozenset(SCOPES)
