"""External MCP connection persistence, `mcp:` ref resolution and probe."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import mcp_client
from app.agents.url_safety import assert_public_http_url
from app.auth.principal import Principal
from app.models import Agent, McpConnection, UserIdentity, utcnow
from app.repos.errors import UnknownRefs
from app.runtime.models import (
    MCP_REF_RE,
    AgentOwner,
    McpConnectionCreate,
    McpConnectionOut,
    McpConnectionUpdate,
    McpToolInfo,
)
from app.settings import get_settings


def _validate_url(url: str) -> None:
    assert_public_http_url(
        url, resolve=False, allowed_hosts=get_settings().mcp_egress_allowlist
    )


def can_edit(conn: McpConnection, p: Principal) -> bool:
    return p.is_superadmin or (conn.owner_kind == p.kind and conn.owner_id == p.id)


def parse_ref(ref: str) -> tuple[str, str] | None:
    """`mcp:<connection-slug>:<tool>` → (connection slug, tool) or None."""
    match = MCP_REF_RE.match(ref)
    if match is None:
        return None
    return match.group(1), match.group(2)


def is_mcp_ref(ref: str) -> bool:
    return ref.startswith("mcp:")


async def _owner_email(session: AsyncSession, conn: McpConnection) -> str | None:
    if conn.owner_kind != "user" or not conn.owner_id:
        return None
    user = await session.get(UserIdentity, conn.owner_id)
    return user.email if user is not None else None


async def to_out(session: AsyncSession, conn: McpConnection) -> McpConnectionOut:
    return McpConnectionOut(
        id=conn.id,
        slug=conn.slug,
        name=conn.name,
        description=conn.description or "",
        url=conn.url,
        header_names=sorted(str(name) for name in (conn.headers or {})),
        timeout_seconds=conn.timeout_seconds,
        enabled=conn.enabled,
        owner=AgentOwner(
            kind=conn.owner_kind,
            id=conn.owner_id,
            email=await _owner_email(session, conn),
        ),
        tools_cache=[McpToolInfo(**tool) for tool in (conn.tools_cache or [])],
        tools_cached_at=conn.tools_cached_at,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


async def list_connections(session: AsyncSession) -> list[McpConnection]:
    stmt = select(McpConnection).order_by(McpConnection.updated_at.desc())
    return list((await session.execute(stmt)).scalars())


async def get_connection(session: AsyncSession, ref: str) -> McpConnection | None:
    stmt = select(McpConnection).where(
        (McpConnection.id == ref) | (McpConnection.slug == ref)
    )
    return (await session.execute(stmt)).scalars().first()


async def create_connection(
    session: AsyncSession, p: Principal, data: McpConnectionCreate
) -> McpConnection:
    _validate_url(data.url)
    existing = (
        await session.execute(
            select(McpConnection.id).where(McpConnection.slug == data.slug)
        )
    ).first()
    if existing is not None:
        raise ValueError("slug already exists")
    conn = McpConnection(
        slug=data.slug,
        name=data.name,
        description=data.description,
        url=data.url,
        headers=dict(data.headers),
        tools_cache=[],
        timeout_seconds=data.timeout_seconds,
        enabled=data.enabled,
        owner_kind=p.kind,
        owner_id=p.id,
    )
    session.add(conn)
    await session.commit()
    await session.refresh(conn)
    return conn


async def update_connection(
    session: AsyncSession, p: Principal, ref: str, data: McpConnectionUpdate
) -> McpConnection:
    conn = await get_connection(session, ref)
    if conn is None:
        raise KeyError("mcp connection not found")
    if not can_edit(conn, p):
        raise PermissionError("mcp connection is read-only for this principal")
    provided = data.model_dump(exclude_unset=True)
    if provided.get("url") is not None:
        _validate_url(str(provided["url"]))
    for field in (
        "name",
        "description",
        "url",
        "headers",
        "timeout_seconds",
        "enabled",
    ):
        value = provided.get(field)
        if value is not None:
            setattr(conn, field, dict(value) if field == "headers" else value)
    conn.updated_at = utcnow()
    await session.commit()
    await session.refresh(conn)
    return conn


async def delete_connection(
    session: AsyncSession, p: Principal, ref: str
) -> list[str]:
    """Delete the connection and strip its `mcp:<slug>:*` refs from every agent."""
    conn = await get_connection(session, ref)
    if conn is None:
        raise KeyError("mcp connection not found")
    if not can_edit(conn, p):
        raise PermissionError("mcp connection is read-only for this principal")
    prefix = f"mcp:{conn.slug}:"
    affected: list[str] = []
    for agent in (await session.execute(select(Agent))).scalars():
        current = list(agent.tools or [])
        remaining = [name for name in current if not name.startswith(prefix)]
        if remaining != current:
            agent.tools = remaining
            agent.updated_at = utcnow()
            affected.append(agent.slug)
    await session.delete(conn)
    await session.commit()
    return sorted(affected)


async def validate_refs(
    session: AsyncSession, p: Principal, names: list[str]
) -> None:
    """Check every `mcp:` ref of an agent: shape, existence, enabled, ownership."""
    refs = [name for name in names if is_mcp_ref(name)]
    if not refs:
        return
    parsed: dict[str, tuple[str, str]] = {}
    for ref in refs:
        parts = parse_ref(ref)
        if parts is None:
            raise ValueError(f"malformed mcp reference: {ref}")
        parsed[ref] = parts
    slugs = {slug for slug, _tool in parsed.values()}
    stmt = select(McpConnection).where(McpConnection.slug.in_(slugs))
    rows = {row.slug: row for row in (await session.execute(stmt)).scalars()}
    missing = sorted(slug for slug in slugs if slug not in rows)
    if missing:
        raise UnknownRefs(f"unknown mcp connections: {', '.join(missing)}")
    disabled = sorted(slug for slug in slugs if not rows[slug].enabled)
    if disabled:
        raise UnknownRefs(f"mcp connections are disabled: {', '.join(disabled)}")
    forbidden = sorted(slug for slug in slugs if not can_edit(rows[slug], p))
    if forbidden:
        raise PermissionError(
            f"mcp connections are read-only for this principal: {', '.join(forbidden)}"
        )


async def resolve_defs(session: AsyncSession, names: list[str]) -> list[dict]:
    """Run-time definitions for `mcp:` refs (resolved on every run)."""
    refs = [name for name in names if is_mcp_ref(name)]
    if not refs:
        return []
    parsed: dict[str, tuple[str, str]] = {}
    for ref in refs:
        parts = parse_ref(ref)
        if parts is None:
            raise UnknownRefs(f"malformed mcp reference: {ref}")
        parsed[ref] = parts
    slugs = {slug for slug, _tool in parsed.values()}
    stmt = select(McpConnection).where(McpConnection.slug.in_(slugs))
    rows = {row.slug: row for row in (await session.execute(stmt)).scalars()}
    missing = sorted(slug for slug in slugs if slug not in rows)
    if missing:
        raise UnknownRefs(f"unknown mcp connections: {', '.join(missing)}")
    disabled = sorted(slug for slug in slugs if not rows[slug].enabled)
    if disabled:
        raise UnknownRefs(f"mcp connections are disabled: {', '.join(disabled)}")
    defs: list[dict] = []
    for ref in refs:
        slug, tool = parsed[ref]
        row = rows[slug]
        defs.append(
            {
                "ref": ref,
                "connection": slug,
                "url": row.url,
                "headers": dict(row.headers or {}),
                "timeout_seconds": row.timeout_seconds,
                "tool": tool,
            }
        )
    return defs


async def probe(
    session: AsyncSession, conn: McpConnection
) -> tuple[list[dict], str | None]:
    """`tools/list` of the external server; caches the result on success."""
    try:
        tools = await mcp_client.list_remote_tools(
            conn.url, dict(conn.headers or {}), float(conn.timeout_seconds)
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the operator as text
        return [], f"error: {mcp_client.describe_error(exc)}"
    conn.tools_cache = tools
    conn.tools_cached_at = utcnow()
    conn.updated_at = utcnow()
    await session.commit()
    await session.refresh(conn)
    return tools, None
