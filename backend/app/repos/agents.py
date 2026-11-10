"""Agent persistence + access rules."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.custom_http import definition_from_row
from app.agents.tools import TOOLS
from app.auth.principal import Principal
from app.models import Agent, AgentVersion, CustomTool, Skill, UserIdentity, utcnow
from app.repos import mcp_connections as mcp_connections_repo
from app.repos import skills as skills_repo
from app.repos import tools as tools_repo
from app.runtime.models import AgentOut, AgentOwner, AgentUpdate, AgentUpsert
from app.settings import get_settings


def _custom_tool_names(tool_refs: list[str]) -> list[str]:
    return [
        name
        for name in tool_refs
        if name not in TOOLS and not str(name).startswith("mcp:")
    ]


def _tool_fingerprint(definition: dict[str, Any]) -> str:
    """Stable fingerprint of a custom-tool definition (as stored in snapshots)."""
    payload = {
        "slug": definition.get("slug"),
        "name": definition.get("name"),
        "description": definition.get("description") or "",
        "method": definition.get("method"),
        "url": definition.get("url"),
        "headers": definition.get("headers") or {},
        "query": definition.get("query") or {},
        "body_template": definition.get("body_template"),
        "content_type": definition.get("content_type") or "application/json",
        "parameters": definition.get("parameters") or [],
        "timeout_seconds": int(definition.get("timeout_seconds") or 20),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _skill_content_fingerprint(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def _stale_flags(
    *,
    agent: Agent,
    snapshot: dict[str, Any] | None,
    live_skills: dict[str, Skill],
    live_tools: dict[str, CustomTool],
) -> tuple[bool, bool]:
    """Compare live skill/tool bodies to the published snapshot defs."""
    if not snapshot:
        return False, False

    snap_skills = {
        str(item.get("slug") or ""): item
        for item in (snapshot.get("skill_defs") or [])
        if isinstance(item, dict) and item.get("slug")
    }
    skills_stale = False
    for slug in agent.skills or []:
        live = live_skills.get(slug)
        if live is None:
            skills_stale = True
            break
        snapped = snap_skills.get(slug)
        if snapped is None:
            skills_stale = True
            break
        if _skill_content_fingerprint(live.content or "") != _skill_content_fingerprint(
            str(snapped.get("content") or "")
        ):
            skills_stale = True
            break

    snap_tools = {
        str(item.get("slug") or item.get("name") or ""): item
        for item in (snapshot.get("tool_defs") or [])
        if isinstance(item, dict) and (item.get("slug") or item.get("name"))
    }
    tools_stale = False
    for slug in _custom_tool_names(list(agent.tools or [])):
        live = live_tools.get(slug)
        if live is None or not live.enabled:
            tools_stale = True
            break
        snapped = snap_tools.get(slug)
        if snapped is None:
            tools_stale = True
            break
        if _tool_fingerprint(definition_from_row(live)) != _tool_fingerprint(snapped):
            tools_stale = True
            break

    return skills_stale, tools_stale


def can_read(agent: Agent, p: Principal) -> bool:
    if p.is_superadmin:
        return True
    if agent.owner_kind == p.kind and agent.owner_id == p.id:
        return True
    return agent.status == "published" and agent.visibility == "shared"


def can_edit(agent: Agent, p: Principal) -> bool:
    return p.is_superadmin or (agent.owner_kind == p.kind and agent.owner_id == p.id)


def can_run(agent: Agent, p: Principal) -> bool:
    if agent.status != "published" or not agent.published_version_id:
        return False
    if agent.visibility == "shared":
        return True
    if agent.owner_kind == p.kind and agent.owner_id == p.id:
        return True
    return p.is_superadmin


async def _find(session: AsyncSession, ref: str) -> Agent | None:
    stmt = select(Agent).where(or_(Agent.id == ref, Agent.slug == ref))
    return (await session.execute(stmt)).scalars().first()


async def resolve_agent(
    session: AsyncSession, ref: str, p: Principal, *, for_run: bool
) -> Agent:
    agent = await _find(session, ref)
    if agent is None or not can_read(agent, p):
        raise KeyError("agent not found")
    if for_run and not can_run(agent, p):
        raise ValueError("agent is not published")
    return agent


async def resolve_editable(session: AsyncSession, ref: str, p: Principal) -> Agent:
    agent = await _find(session, ref)
    if agent is None:
        raise KeyError("agent not found")
    if not can_edit(agent, p):
        raise PermissionError("agent is read-only for this principal")
    return agent


async def _owner_email(session: AsyncSession, agent: Agent) -> str | None:
    if agent.owner_kind != "user" or not agent.owner_id:
        return None
    user = await session.get(UserIdentity, agent.owner_id)
    return user.email if user is not None else None


async def _published_version(session: AsyncSession, agent: Agent) -> AgentVersion | None:
    if not agent.published_version_id:
        return None
    return await session.get(AgentVersion, agent.published_version_id)


async def to_out_many(session: AsyncSession, agents: list[Agent]) -> list[AgentOut]:
    """Serialize agents with batch-loaded stale flags (skills/tools vs published snapshot)."""
    if not agents:
        return []

    version_ids = [agent.published_version_id for agent in agents if agent.published_version_id]
    versions: dict[str, AgentVersion] = {}
    if version_ids:
        rows = (
            await session.execute(select(AgentVersion).where(AgentVersion.id.in_(version_ids)))
        ).scalars()
        versions = {row.id: row for row in rows}

    skill_slugs: set[str] = set()
    tool_slugs: set[str] = set()
    for agent in agents:
        skill_slugs.update(str(name) for name in (agent.skills or []))
        tool_slugs.update(_custom_tool_names(list(agent.tools or [])))

    live_skills: dict[str, Skill] = {}
    if skill_slugs:
        for row in (
            await session.execute(select(Skill).where(Skill.slug.in_(skill_slugs)))
        ).scalars():
            live_skills[row.slug] = row

    live_tools: dict[str, CustomTool] = {}
    if tool_slugs:
        for row in (
            await session.execute(select(CustomTool).where(CustomTool.slug.in_(tool_slugs)))
        ).scalars():
            live_tools[row.slug] = row

    owner_ids = {
        agent.owner_id
        for agent in agents
        if agent.owner_kind == "user" and agent.owner_id
    }
    emails: dict[str, str | None] = {}
    if owner_ids:
        for user in (
            await session.execute(select(UserIdentity).where(UserIdentity.sub.in_(owner_ids)))
        ).scalars():
            emails[user.sub] = user.email

    items: list[AgentOut] = []
    for agent in agents:
        version = (
            versions.get(agent.published_version_id)
            if agent.published_version_id
            else None
        )
        snapshot = dict(version.snapshot or {}) if version is not None else None
        skills_stale, tools_stale = _stale_flags(
            agent=agent,
            snapshot=snapshot,
            live_skills=live_skills,
            live_tools=live_tools,
        )
        items.append(
            AgentOut(
                id=agent.id,
                slug=agent.slug,
                name=agent.name,
                description=agent.description or "",
                kind=agent.kind,
                plugin_name=agent.plugin_name,
                system_prompt=agent.system_prompt or "",
                tools=list(agent.tools or []),
                skills=list(agent.skills or []),
                sub_agents=list(agent.sub_agents or []),
                memory_enabled=bool(agent.memory_enabled),
                llm=dict(agent.llm or {}),
                limits=dict(agent.limits or {}),
                visibility=agent.visibility,
                status=agent.status,
                published_version=version.version if version is not None else None,
                skills_stale=skills_stale,
                tools_stale=tools_stale,
                owner=AgentOwner(
                    kind=agent.owner_kind,
                    id=agent.owner_id,
                    email=emails.get(agent.owner_id) if agent.owner_kind == "user" else None,
                ),
                created_at=agent.created_at,
                updated_at=agent.updated_at,
            )
        )
    return items


async def to_out(session: AsyncSession, agent: Agent) -> AgentOut:
    return (await to_out_many(session, [agent]))[0]


def _agents_scope_stmt(p: Principal, *, scope: str, q: str | None):
    stmt = select(Agent)
    if scope == "owned":
        stmt = stmt.where(
            Agent.owner_kind == p.kind,
            Agent.owner_id == p.id,
            Agent.status != "archived",
        )
    elif scope == "shared":
        # Все published+shared, включая свои — иначе вкладка «Общие» и MCP allowlist
        # пустеют для владельца (бейдж «общий» есть, а в списке нет).
        stmt = stmt.where(Agent.visibility == "shared", Agent.status == "published")
    elif scope == "archived":
        stmt = stmt.where(Agent.status == "archived")
        if not p.is_superadmin:
            stmt = stmt.where(Agent.owner_kind == p.kind, Agent.owner_id == p.id)
    else:
        stmt = stmt.where(Agent.status != "archived")
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(or_(Agent.name.ilike(pattern), Agent.slug.ilike(pattern)))
    return stmt.order_by(Agent.updated_at.desc())


async def list_agents(
    session: AsyncSession,
    p: Principal,
    *,
    scope: str,
    q: str | None,
    limit: int,
    offset: int,
    stale: str | None = None,
) -> tuple[list[Agent], int, list[AgentOut] | None]:
    """Return agents page. If `stale` is set, also return precomputed AgentOut list (filtered)."""
    stmt = _agents_scope_stmt(p, scope=scope, q=q)
    if not stale:
        total = (
            await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))
        ).scalar_one()
        page = stmt.limit(limit).offset(offset)
        rows = list((await session.execute(page)).scalars())
        return rows, int(total), None

    # Stale filter needs flags → load scope rows (cap), filter, then paginate in memory.
    rows = list((await session.execute(stmt.limit(500))).scalars())
    outs = await to_out_many(session, rows)
    if stale == "skills":
        outs = [item for item in outs if item.skills_stale]
    elif stale == "tools":
        outs = [item for item in outs if item.tools_stale]
    else:
        outs = [item for item in outs if item.skills_stale or item.tools_stale]
    # Prefer stale first (already filtered); keep updated_at order from query.
    total = len(outs)
    page_outs = outs[offset : offset + limit]
    slug_set = {item.slug for item in page_outs}
    page_rows = [agent for agent in rows if agent.slug in slug_set]
    # Preserve filtered order
    by_slug = {agent.slug: agent for agent in page_rows}
    ordered = [by_slug[item.slug] for item in page_outs if item.slug in by_slug]
    return ordered, total, page_outs


def _default_limits() -> dict[str, Any]:
    settings = get_settings()
    return {
        "max_steps": settings.max_steps,
        "timeout_seconds": settings.run_timeout_seconds,
    }


async def _snapshot(session: AsyncSession, agent: Agent) -> dict[str, Any]:
    """Freeze agent config + referenced tool/skill definitions into a version."""
    tool_defs = await tools_repo.definitions_for(session, list(agent.tools or []))
    skill_rows = await skills_repo.resolve_skill_refs(session, list(agent.skills or []))
    return {
        "name": agent.name,
        "description": agent.description,
        "kind": agent.kind,
        "plugin_name": agent.plugin_name,
        "system_prompt": agent.system_prompt,
        "tools": list(agent.tools or []),
        "skills": list(agent.skills or []),
        "sub_agents": list(agent.sub_agents or []),
        "tool_defs": tool_defs,
        "skill_defs": [skills_repo.skill_definition(row) for row in skill_rows],
        "llm": dict(agent.llm or {}),
        "limits": dict(agent.limits or {}),
    }


async def new_version(
    session: AsyncSession, agent: Agent, *, created_by: str
) -> AgentVersion:
    stmt = select(func.max(AgentVersion.version)).where(AgentVersion.agent_id == agent.id)
    current = (await session.execute(stmt)).scalar_one_or_none() or 0
    version = AgentVersion(
        agent_id=agent.id,
        version=current + 1,
        snapshot=await _snapshot(session, agent),
        created_by=created_by,
    )
    session.add(version)
    await session.flush()
    return version


async def create_agent(
    session: AsyncSession, p: Principal, data: AgentUpsert
) -> Agent:
    await tools_repo.resolve_tool_refs(session, list(data.tools))
    await mcp_connections_repo.validate_refs(session, p, list(data.tools))
    await skills_repo.resolve_skill_refs(session, list(data.skills))
    existing = (await session.execute(select(Agent.id).where(Agent.slug == data.slug))).first()
    if existing is not None:
        raise ValueError("slug already exists")
    agent = Agent(
        slug=data.slug,
        name=data.name,
        description=data.description,
        kind=data.kind,
        plugin_name=data.plugin_name,
        system_prompt=data.system_prompt,
        tools=list(data.tools),
        skills=list(data.skills),
        sub_agents=list(data.sub_agents),
        memory_enabled=bool(data.memory_enabled),
        llm=dict(data.llm),
        limits={**_default_limits(), **data.limits},
        owner_kind=p.kind,
        owner_id=p.id,
        tenant_id=p.tenant_id,
        visibility="private",
        status="draft",
        published_version_id=None,
    )
    session.add(agent)
    await session.flush()
    if data.kind == "plugin":
        version = await new_version(session, agent, created_by=p.id)
        agent.status = "published"
        agent.published_version_id = version.id
    await session.commit()
    await session.refresh(agent)
    return agent


def _merged_config(agent: Agent, data: AgentUpdate) -> dict[str, Any]:
    provided = data.model_dump(exclude_unset=True)
    merged = {
        "slug": agent.slug,
        "name": agent.name,
        "description": agent.description or "",
        "kind": agent.kind,
        "plugin_name": agent.plugin_name,
        "system_prompt": agent.system_prompt or "",
        "tools": list(agent.tools or []),
        "skills": list(agent.skills or []),
        "sub_agents": list(agent.sub_agents or []),
        "memory_enabled": bool(agent.memory_enabled),
        "llm": dict(agent.llm or {}),
        "limits": dict(agent.limits or {}),
    }
    merged.update(provided)
    return merged


async def update_agent(
    session: AsyncSession, p: Principal, agent_id: str, data: AgentUpdate
) -> Agent:
    agent = await resolve_editable(session, agent_id, p)
    if data.slug is not None and data.slug != agent.slug:
        raise ValueError("slug is immutable")
    config = AgentUpsert(**_merged_config(agent, data))
    await tools_repo.resolve_tool_refs(session, list(config.tools))
    await mcp_connections_repo.validate_refs(session, p, list(config.tools))
    await skills_repo.resolve_skill_refs(session, list(config.skills))
    for field in ("name", "description", "kind", "plugin_name", "system_prompt"):
        setattr(agent, field, getattr(config, field))
    agent.tools = list(config.tools)
    agent.skills = list(config.skills)
    agent.sub_agents = list(config.sub_agents)
    agent.memory_enabled = bool(config.memory_enabled)
    agent.llm = dict(config.llm)
    agent.limits = {**_default_limits(), **config.limits}
    agent.updated_at = utcnow()
    await session.commit()
    await session.refresh(agent)
    return agent


async def publish_agent(
    session: AsyncSession, p: Principal, agent_id: str, visibility: str
) -> tuple[Agent, AgentVersion]:
    agent = await resolve_editable(session, agent_id, p)
    version = await new_version(session, agent, created_by=p.id)
    agent.status = "published"
    agent.visibility = visibility
    agent.published_version_id = version.id
    agent.updated_at = utcnow()
    await session.commit()
    await session.refresh(agent)
    await session.refresh(version)
    return agent, version


async def rollback_agent(
    session: AsyncSession,
    p: Principal,
    agent_id: str,
    version_number: int,
    visibility: str | None = None,
) -> tuple[Agent, AgentVersion]:
    """Restore a snapshot as a NEW version (history stays append-only)."""
    agent = await resolve_editable(session, agent_id, p)
    source = (
        await session.execute(
            select(AgentVersion).where(
                AgentVersion.agent_id == agent.id,
                AgentVersion.version == version_number,
            )
        )
    ).scalars().first()
    if source is None:
        raise KeyError(f"version {version_number} not found")

    snapshot = dict(source.snapshot or {})
    agent.name = str(snapshot.get("name") or agent.name)
    agent.description = str(snapshot.get("description") or "")
    agent.kind = str(snapshot.get("kind") or agent.kind)
    agent.plugin_name = snapshot.get("plugin_name")
    agent.system_prompt = str(snapshot.get("system_prompt") or "")
    agent.tools = list(snapshot.get("tools") or [])
    agent.skills = list(snapshot.get("skills") or [])
    agent.llm = dict(snapshot.get("llm") or {})
    agent.limits = {**_default_limits(), **(snapshot.get("limits") or {})}
    await tools_repo.resolve_tool_refs(session, list(agent.tools))
    await mcp_connections_repo.validate_refs(session, p, list(agent.tools))
    await skills_repo.resolve_skill_refs(session, list(agent.skills))

    version = await new_version(session, agent, created_by=p.id)
    agent.status = "published"
    if visibility:
        agent.visibility = visibility
    agent.published_version_id = version.id
    agent.updated_at = utcnow()
    await session.commit()
    await session.refresh(agent)
    await session.refresh(version)
    return agent, version


async def archive_agent(session: AsyncSession, p: Principal, agent_id: str) -> Agent:
    agent = await resolve_editable(session, agent_id, p)
    agent.status = "archived"
    agent.updated_at = utcnow()
    await session.commit()
    await session.refresh(agent)
    return agent


async def purge_agent(session: AsyncSession, p: Principal, agent_id: str) -> str:
    """Безвозвратно удалить агента (только из архива). Версии — CASCADE, runs — SET NULL."""
    agent = await resolve_editable(session, agent_id, p)
    if agent.status != "archived":
        raise ValueError("only archived agents can be permanently deleted; archive first")
    slug = agent.slug
    await session.delete(agent)
    await session.commit()
    return slug


async def clone_agent(session: AsyncSession, p: Principal, agent_id: str) -> Agent:
    source = await resolve_agent(session, agent_id, p, for_run=False)
    clone = Agent(
        slug=f"{source.slug}-copy-{uuid4().hex[:6]}",
        name=f"{source.name} (copy)",
        description=source.description,
        kind=source.kind,
        plugin_name=source.plugin_name,
        system_prompt=source.system_prompt,
        tools=list(source.tools or []),
        skills=list(source.skills or []),
        sub_agents=list(source.sub_agents or []),
        memory_enabled=bool(source.memory_enabled),
        llm=dict(source.llm or {}),
        limits=dict(source.limits or {}),
        owner_kind=p.kind,
        owner_id=p.id,
        tenant_id=p.tenant_id,
        visibility="private",
        status="draft",
        published_version_id=None,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(clone)
    await session.commit()
    await session.refresh(clone)
    return clone


async def list_versions(
    session: AsyncSession, p: Principal, agent_id: str
) -> list[AgentVersion]:
    agent = await resolve_agent(session, agent_id, p, for_run=False)
    stmt = (
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent.id)
        .order_by(AgentVersion.version.desc())
    )
    return list((await session.execute(stmt)).scalars())


async def get_version(session: AsyncSession, agent: Agent) -> AgentVersion | None:
    return await _published_version(session, agent)
