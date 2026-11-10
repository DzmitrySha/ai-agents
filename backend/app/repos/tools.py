"""Custom (no-code) tool persistence and resolution."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.custom_http import definition_from_row, invoke, json_schema
from app.agents.tools import TOOLS
from app.agents.url_safety import assert_public_http_url
from app.auth.principal import Principal
from app.models import Agent, AgentVersion, CustomTool, UserIdentity, utcnow
from app.repos.errors import UnknownRefs
from app.runtime.models import (
    AgentOwner,
    ToolCreate,
    ToolOut,
    ToolParam,
    ToolTestResult,
    ToolUpdate,
    ToolUsageOut,
    ToolUserAgent,
)


def _validate_tool_url(url: str) -> None:
    assert_public_http_url(url, resolve=False)


def can_edit_tool(tool: CustomTool, p: Principal) -> bool:
    return p.is_superadmin or (tool.owner_kind == p.kind and tool.owner_id == p.id)


async def _owner_email(session: AsyncSession, tool: CustomTool) -> str | None:
    if tool.owner_kind != "user" or not tool.owner_id:
        return None
    user = await session.get(UserIdentity, tool.owner_id)
    return user.email if user is not None else None


async def to_out(session: AsyncSession, tool: CustomTool) -> ToolOut:
    return ToolOut(
        id=tool.id,
        slug=tool.slug,
        name=tool.name,
        description=tool.description or "",
        kind=tool.kind,
        method=tool.method,
        url=tool.url,
        header_names=sorted(str(name) for name in (tool.headers or {})),
        query=dict(tool.query or {}),
        body_template=tool.body_template,
        content_type=tool.content_type,
        parameters=[ToolParam(**param) for param in tool.parameters or []],
        timeout_seconds=tool.timeout_seconds,
        enabled=tool.enabled,
        owner=AgentOwner(
            kind=tool.owner_kind,
            id=tool.owner_id,
            email=await _owner_email(session, tool),
        ),
        created_at=tool.created_at,
        updated_at=tool.updated_at,
    )


async def get_tool(session: AsyncSession, ref: str) -> CustomTool | None:
    stmt = select(CustomTool).where(
        (CustomTool.id == ref) | (CustomTool.slug == ref)
    )
    return (await session.execute(stmt)).scalars().first()


async def list_tools(
    session: AsyncSession, *, q: str | None = None, include_disabled: bool = True
) -> list[CustomTool]:
    stmt = select(CustomTool)
    if not include_disabled:
        stmt = stmt.where(CustomTool.enabled.is_(True))
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            (CustomTool.name.ilike(pattern)) | (CustomTool.slug.ilike(pattern))
        )
    stmt = stmt.order_by(CustomTool.updated_at.desc())
    return list((await session.execute(stmt)).scalars())


async def create_tool(session: AsyncSession, p: Principal, data: ToolCreate) -> CustomTool:
    if data.slug in TOOLS:
        raise ValueError(f"slug {data.slug!r} is reserved by a builtin tool")
    _validate_tool_url(data.url)
    existing = (
        await session.execute(select(CustomTool.id).where(CustomTool.slug == data.slug))
    ).first()
    if existing is not None:
        raise ValueError("slug already exists")
    tool = CustomTool(
        slug=data.slug,
        name=data.name,
        description=data.description,
        kind="http",
        method=data.method,
        url=data.url,
        headers=dict(data.headers),
        query=dict(data.query),
        body_template=data.body_template,
        content_type=data.content_type,
        parameters=[param.model_dump() for param in data.parameters],
        timeout_seconds=data.timeout_seconds,
        enabled=data.enabled,
        owner_kind=p.kind,
        owner_id=p.id,
    )
    session.add(tool)
    await session.commit()
    await session.refresh(tool)
    return tool


async def update_tool(
    session: AsyncSession, p: Principal, ref: str, data: ToolUpdate
) -> CustomTool:
    tool = await get_tool(session, ref)
    if tool is None:
        raise KeyError("tool not found")
    if not can_edit_tool(tool, p):
        raise PermissionError("tool is read-only for this principal")
    provided = data.model_dump(exclude_unset=True)
    if "url" in provided and provided["url"] is not None:
        _validate_tool_url(str(provided["url"]))
    if "parameters" in provided and provided["parameters"] is not None:
        provided["parameters"] = [
            param.model_dump() if hasattr(param, "model_dump") else param
            for param in provided["parameters"]
        ]
    for field, value in provided.items():
        if field == "headers" and value is not None:
            setattr(tool, field, dict(value))
        else:
            setattr(tool, field, value)
    tool.updated_at = utcnow()
    await session.commit()
    await session.refresh(tool)
    return tool


async def agents_using(session: AsyncSession, slug: str) -> list[Agent]:
    """Every agent whose current tool list references `slug` (draft or published)."""
    rows = list((await session.execute(select(Agent))).scalars())
    return [agent for agent in rows if slug in (agent.tools or [])]


async def tool_usage(session: AsyncSession, ref: str) -> ToolUsageOut | None:
    tool = await get_tool(session, ref)
    if tool is None:
        return None
    agents = sorted(await agents_using(session, tool.slug), key=lambda item: item.slug)
    version_ids = [agent.published_version_id for agent in agents if agent.published_version_id]
    numbers: dict[str, int] = {}
    if version_ids:
        rows = await session.execute(
            select(AgentVersion.id, AgentVersion.version).where(
                AgentVersion.id.in_(version_ids)
            )
        )
        numbers = {str(row[0]): int(row[1]) for row in rows}
    return ToolUsageOut(
        slug=tool.slug,
        total=len(agents),
        agents=[
            ToolUserAgent(
                slug=agent.slug,
                name=agent.name,
                status=agent.status,
                published_version=numbers.get(agent.published_version_id or ""),
            )
            for agent in agents
        ],
    )


async def delete_tool(session: AsyncSession, p: Principal, ref: str) -> list[str]:
    """Delete the tool and detach it from every agent that references it.

    Published versions keep their frozen snapshot (history), but runs resolve the
    current tool list, so detaching here is what actually removes the call.
    """
    tool = await get_tool(session, ref)
    if tool is None:
        raise KeyError("tool not found")
    if not can_edit_tool(tool, p):
        raise PermissionError("tool is read-only for this principal")
    affected = sorted(await agents_using(session, tool.slug), key=lambda item: item.slug)
    for agent in affected:
        remaining = [name for name in (agent.tools or []) if name != tool.slug]
        if remaining != (agent.tools or []):
            agent.tools = remaining
            agent.updated_at = utcnow()
    await session.delete(tool)
    await session.commit()
    return [agent.slug for agent in affected]


async def test_tool(tool: CustomTool, params: dict) -> ToolTestResult:
    output = await invoke(definition_from_row(tool), params)
    ok = not output.startswith("error:")
    status: int | None = None
    if output.startswith("error: HTTP "):
        digits = "".join(ch for ch in output[len("error: HTTP ") :].split(":", 1)[0] if ch.isdigit())
        status = int(digits) if digits else None
    return ToolTestResult(ok=ok, status=status, output=output)


async def invoke_by_name(
    session: AsyncSession, name: str, params: dict
) -> ToolTestResult:
    """Execute builtin or enabled custom tool without starting an agent run."""
    from app.agents.tools import TOOLS

    if name in TOOLS:
        tool_obj = TOOLS[name]
        try:
            raw = await tool_obj.ainvoke(params or {})
        except Exception as exc:  # noqa: BLE001 - surface to caller as text
            return ToolTestResult(ok=False, status=None, output=f"error: {exc}")
        output = raw if isinstance(raw, str) else str(raw)
        return ToolTestResult(
            ok=not output.startswith("error:"), status=None, output=output
        )
    tool = await get_tool(session, name)
    if tool is None or not tool.enabled:
        raise KeyError("tool not found")
    return await test_tool(tool, params)


async def resolve_tool_refs(session: AsyncSession, names: list[str]) -> list[str]:
    """Return custom tool slugs referenced by the agent (builtins are validated later)."""
    custom_names = [
        name for name in names if name not in TOOLS and not name.startswith("mcp:")
    ]
    if not custom_names:
        return []
    stmt = select(CustomTool).where(CustomTool.slug.in_(custom_names))
    rows = {row.slug: row for row in (await session.execute(stmt)).scalars()}
    missing = [name for name in custom_names if name not in rows]
    if missing:
        raise UnknownRefs(f"unknown tools: {', '.join(sorted(missing))}")
    disabled = [name for name in custom_names if not rows[name].enabled]
    if disabled:
        raise UnknownRefs(f"tools are disabled: {', '.join(sorted(disabled))}")
    return custom_names


async def definitions_for(session: AsyncSession, names: list[str]) -> list[dict]:
    """Current custom-tool definitions for the given tool names (resolved at run start)."""
    custom_names = [
        name for name in names if name not in TOOLS and not name.startswith("mcp:")
    ]
    if not custom_names:
        return []
    stmt = select(CustomTool).where(CustomTool.slug.in_(custom_names))
    rows = {row.slug: row for row in (await session.execute(stmt)).scalars()}
    missing = [name for name in custom_names if name not in rows]
    if missing:
        raise UnknownRefs(f"unknown tools: {', '.join(sorted(missing))}")
    disabled = [name for name in custom_names if not rows[name].enabled]
    if disabled:
        raise UnknownRefs(f"tools are disabled: {', '.join(sorted(disabled))}")
    return [definition_from_row(rows[name]) for name in custom_names]


async def tool_specs(session: AsyncSession) -> list[dict]:
    from app.agents.tools import TOOL_SPECS

    specs = [dict(spec, source="builtin") for spec in TOOL_SPECS]
    for tool in await list_tools(session, include_disabled=False):
        specs.append(
            {
                "name": tool.slug,
                "description": tool.description or tool.name,
                "parameters": json_schema(list(tool.parameters or [])),
                "source": "custom",
            }
        )
    return specs
