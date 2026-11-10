"""Opt-in agent memory storage."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, cast, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentMemoryRow, utcnow
from app.runtime.models import AgentMemoryOut

MAX_CONTENT = 4000
MAX_ITEMS = 200


def to_out(row: AgentMemoryRow) -> AgentMemoryOut:
    return AgentMemoryOut(
        id=row.id,
        agent_id=row.agent_id,
        namespace=row.namespace,
        key=row.key,
        content=row.content,
        tags=list(row.tags or []),
        created_at=row.created_at,
        updated_at=row.updated_at,
        expires_at=row.expires_at,
    )


def _scope(
    *,
    agent_id: str,
    principal_kind: str,
    principal_id: str,
    namespace: str,
):
    return (
        AgentMemoryRow.agent_id == agent_id,
        AgentMemoryRow.principal_kind == principal_kind,
        AgentMemoryRow.principal_id == principal_id,
        AgentMemoryRow.namespace == namespace,
    )


async def write(
    session: AsyncSession,
    *,
    agent_id: str,
    principal_kind: str,
    principal_id: str,
    namespace: str,
    key: str,
    content: str,
    tags: list[str] | None = None,
    expires_at: datetime | None = None,
) -> AgentMemoryRow:
    clean_content = content.strip()[:MAX_CONTENT]
    if not key.strip() or not clean_content:
        raise ValueError("memory key and content are required")
    stmt = select(AgentMemoryRow).where(
        *_scope(
            agent_id=agent_id,
            principal_kind=principal_kind,
            principal_id=principal_id,
            namespace=namespace,
        ),
        AgentMemoryRow.key == key.strip()[:200],
    )
    row = (await session.execute(stmt)).scalars().first()
    if row is None:
        row = AgentMemoryRow(
            agent_id=agent_id,
            principal_kind=principal_kind,
            principal_id=principal_id,
            namespace=namespace,
            key=key.strip()[:200],
            content=clean_content,
            tags=list(tags or [])[:20],
            expires_at=expires_at,
        )
        session.add(row)
    else:
        row.content = clean_content
        row.tags = list(tags or [])[:20]
        row.expires_at = expires_at
        row.updated_at = utcnow()
    await session.commit()
    await session.refresh(row)
    return row


async def search(
    session: AsyncSession,
    *,
    agent_id: str,
    principal_kind: str,
    principal_id: str,
    namespace: str,
    query: str,
    limit: int = 5,
) -> list[AgentMemoryRow]:
    pattern = f"%{query.strip()}%"
    stmt = (
        select(AgentMemoryRow)
        .where(
            *_scope(
                agent_id=agent_id,
                principal_kind=principal_kind,
                principal_id=principal_id,
                namespace=namespace,
            ),
            or_(
                AgentMemoryRow.key.ilike(pattern),
                AgentMemoryRow.content.ilike(pattern),
                cast(AgentMemoryRow.tags, String).ilike(pattern),
            ),
            or_(
                AgentMemoryRow.expires_at.is_(None),
                AgentMemoryRow.expires_at > utcnow(),
            ),
        )
        .order_by(AgentMemoryRow.updated_at.desc())
        .limit(max(1, min(int(limit), 20)))
    )
    return list((await session.execute(stmt)).scalars())


async def delete_key(
    session: AsyncSession,
    *,
    agent_id: str,
    principal_kind: str,
    principal_id: str,
    namespace: str,
    key: str,
) -> bool:
    result = await session.execute(
        delete(AgentMemoryRow).where(
            *_scope(
                agent_id=agent_id,
                principal_kind=principal_kind,
                principal_id=principal_id,
                namespace=namespace,
            ),
            AgentMemoryRow.key == key.strip()[:200],
        )
    )
    await session.commit()
    return bool(result.rowcount)


async def list_for_agent(
    session: AsyncSession,
    agent_id: str,
    *,
    principal_kind: str | None = None,
    principal_id: str | None = None,
) -> list[AgentMemoryRow]:
    stmt = select(AgentMemoryRow).where(AgentMemoryRow.agent_id == agent_id)
    if principal_kind is not None:
        stmt = stmt.where(AgentMemoryRow.principal_kind == principal_kind)
    if principal_id is not None:
        stmt = stmt.where(AgentMemoryRow.principal_id == principal_id)
    stmt = stmt.order_by(AgentMemoryRow.updated_at.desc()).limit(MAX_ITEMS)
    return list((await session.execute(stmt)).scalars())


async def delete_entry(
    session: AsyncSession, agent_id: str, memory_id: str
) -> bool:
    row = await session.get(AgentMemoryRow, memory_id)
    if row is None or row.agent_id != agent_id:
        return False
    await session.delete(row)
    await session.commit()
    return True
