"""Service key persistence: create/list/update/revoke + Bearer lookup."""

from __future__ import annotations

import hashlib
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import Principal, normalize_scopes
from app.models import ServiceKey, utcnow
from app.repos.allowlists import (
    validate_agent_slugs,
    validate_skill_slugs,
    validate_tool_slugs,
)

KEY_PREFIX = "sk-ag-"


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _principal(row: ServiceKey) -> Principal:
    scopes = normalize_scopes(row.scopes or [])
    return Principal(
        kind="service",
        id=row.id,
        is_superadmin="admin" in scopes,
        scopes=scopes,
        catalog_restricted=True,
        agent_slugs=tuple(row.agent_slugs or []),
        tool_slugs=tuple(row.tool_slugs or []),
        skill_slugs=tuple(row.skill_slugs or []),
    )


async def create_key(
    session: AsyncSession,
    *,
    created_by: str,
    name: str,
    scopes: list[str],
    agent_slugs: list[str] | None = None,
    tool_slugs: list[str] | None = None,
    skill_slugs: list[str] | None = None,
) -> tuple[ServiceKey, str]:
    agents = await validate_agent_slugs(session, list(agent_slugs or []))
    tools = await validate_tool_slugs(session, list(tool_slugs or []))
    skills = await validate_skill_slugs(session, list(skill_slugs or []))
    raw = KEY_PREFIX + secrets.token_urlsafe(32)
    normalized = sorted(normalize_scopes(scopes))
    row = ServiceKey(
        name=name,
        key_hash=hash_key(raw),
        scopes=normalized,
        agent_slugs=agents,
        tool_slugs=tools,
        skill_slugs=skills,
        created_by=created_by,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row, raw


async def update_key(session: AsyncSession, key_id: str, data) -> ServiceKey:
    row = await session.get(ServiceKey, key_id)
    if row is None:
        raise KeyError("service key not found")
    provided = data.model_dump(exclude_unset=True) if hasattr(data, "model_dump") else dict(data)
    if "name" in provided and provided["name"] is not None:
        row.name = provided["name"]
    if "scopes" in provided and provided["scopes"] is not None:
        row.scopes = sorted(normalize_scopes(provided["scopes"]))
    if "enabled" in provided and provided["enabled"] is not None:
        row.enabled = bool(provided["enabled"])
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
    await session.commit()
    await session.refresh(row)
    return row


async def list_keys(session: AsyncSession) -> list[ServiceKey]:
    stmt = select(ServiceKey).order_by(ServiceKey.created_at.desc())
    return list((await session.execute(stmt)).scalars())


async def revoke_key(session: AsyncSession, key_id: str) -> ServiceKey | None:
    row = await session.get(ServiceKey, key_id)
    if row is None:
        return None
    row.enabled = False
    await session.commit()
    await session.refresh(row)
    return row


async def delete_key(session: AsyncSession, key_id: str) -> bool:
    row = await session.get(ServiceKey, key_id)
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def authenticate(session: AsyncSession, raw: str) -> Principal | None:
    stmt = select(ServiceKey).where(
        ServiceKey.key_hash == hash_key(raw), ServiceKey.enabled.is_(True)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    row.last_used_at = utcnow()
    await session.commit()
    return _principal(row)
