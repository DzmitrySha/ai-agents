"""MCP server (public `/mcp` access keys) persistence + bearer lookup."""

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import McpServer, utcnow
from app.repos.allowlists import (
    validate_agent_slugs,
    validate_skill_slugs,
    validate_tool_slugs,
)
from app.repos.service_keys import hash_key

KEY_PREFIX = "mcp-ag-"


def _new_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


async def create_server(
    session: AsyncSession,
    *,
    created_by: str,
    slug: str,
    name: str,
    description: str = "",
    agent_slugs: list[str] | None = None,
    tool_slugs: list[str] | None = None,
    skill_slugs: list[str] | None = None,
) -> tuple[McpServer, str]:
    agents = await validate_agent_slugs(session, list(agent_slugs or []))
    tools = await validate_tool_slugs(session, list(tool_slugs or []))
    skills = await validate_skill_slugs(session, list(skill_slugs or []))
    raw = _new_key()
    row = McpServer(
        slug=slug,
        name=name,
        description=description,
        key_hash=hash_key(raw),
        agent_slugs=agents,
        tool_slugs=tools,
        skill_slugs=skills,
        created_by=created_by,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row, raw


async def list_servers(session: AsyncSession) -> list[McpServer]:
    stmt = select(McpServer).order_by(McpServer.created_at.desc())
    return list((await session.execute(stmt)).scalars())


async def get_server(session: AsyncSession, ref: str) -> McpServer | None:
    stmt = select(McpServer).where((McpServer.id == ref) | (McpServer.slug == ref))
    return (await session.execute(stmt)).scalars().first()


async def update_server(
    session: AsyncSession, ref: str, data, *, rotate_key: bool = False
) -> tuple[McpServer, str | None]:
    row = await get_server(session, ref)
    if row is None:
        raise KeyError("mcp server not found")
    provided = data.model_dump(exclude_unset=True) if hasattr(data, "model_dump") else dict(data)
    for field in ("name", "description", "enabled"):
        value = provided.get(field)
        if value is not None:
            setattr(row, field, value)
    if "agent_slugs" in provided and provided["agent_slugs"] is not None:
        row.agent_slugs = await validate_agent_slugs(
            session, list(provided["agent_slugs"] or [])
        )
    if "tool_slugs" in provided and provided["tool_slugs"] is not None:
        row.tool_slugs = await validate_tool_slugs(
            session, list(provided["tool_slugs"] or [])
        )
    if "skill_slugs" in provided and provided["skill_slugs"] is not None:
        row.skill_slugs = await validate_skill_slugs(
            session, list(provided["skill_slugs"] or [])
        )
    raw: str | None = None
    if rotate_key:
        raw = _new_key()
        row.key_hash = hash_key(raw)
    row.updated_at = utcnow()
    await session.commit()
    await session.refresh(row)
    return row, raw


async def delete_server(session: AsyncSession, ref: str) -> bool:
    row = await get_server(session, ref)
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def authenticate(session: AsyncSession, raw: str) -> McpServer | None:
    stmt = select(McpServer).where(
        McpServer.key_hash == hash_key(raw), McpServer.enabled.is_(True)
    )
    row = (await session.execute(stmt)).scalars().first()
    if row is None:
        return None
    row.last_used_at = utcnow()
    await session.commit()
    return row
