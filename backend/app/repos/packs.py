"""Pack installation: validate refs, diff, then create/update pack agents atomically."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import Principal
from app.models import Agent, CustomPack, PackInstall, utcnow
from app.repos import agents as agents_repo
from app.repos import mcp_connections as mcp_connections_repo
from app.repos import skills as skills_repo
from app.repos import tools as tools_repo
from app.repos.errors import UnknownRefs
from app.runtime.models import (
    AgentUpsert,
    PackChange,
    PackInstallResult,
    PackManifest,
    PackOut,
)
from app.settings import get_settings


class PackValidationError(ValueError):
    """Manifest references an unknown/disabled/foreign entity."""


class PackConflict(ValueError):
    """A pack agent slug is already owned by another pack or a user."""


def _default_limits() -> dict[str, Any]:
    settings = get_settings()
    return {
        "max_steps": settings.max_steps,
        "timeout_seconds": settings.run_timeout_seconds,
    }


async def installed_versions(session: AsyncSession) -> dict[str, list[str]]:
    rows = (
        await session.execute(
            select(PackInstall).order_by(PackInstall.installed_at.asc())
        )
    ).scalars()
    result: dict[str, list[str]] = {}
    for row in rows:
        result.setdefault(row.name, []).append(row.version)
    return result


async def to_out(
    session: AsyncSession,
    manifest: PackManifest,
    *,
    source: str = "code",
) -> PackOut:
    versions = (await installed_versions(session)).get(manifest.name, [])
    return PackOut(
        name=manifest.name,
        version=manifest.version,
        description=manifest.description,
        source=source,
        agents=[agent.slug for agent in manifest.agents],
        skills=list(manifest.skills),
        tools=list(manifest.tools),
        installed_versions=versions,
    )


async def list_custom(session: AsyncSession) -> list[PackManifest]:
    rows = (
        await session.execute(select(CustomPack).order_by(CustomPack.name.asc()))
    ).scalars()
    return [PackManifest.model_validate(row.manifest) for row in rows]


async def get_custom(session: AsyncSession, name: str) -> PackManifest | None:
    row = (
        await session.execute(select(CustomPack).where(CustomPack.name == name))
    ).scalars().first()
    return PackManifest.model_validate(row.manifest) if row is not None else None


async def create_custom(
    session: AsyncSession, principal: Principal, manifest: PackManifest
) -> None:
    session.add(
        CustomPack(
            name=manifest.name,
            manifest=manifest.model_dump(mode="json"),
            created_by=principal.id,
        )
    )
    await session.commit()


async def update_custom(
    session: AsyncSession, name: str, manifest: PackManifest
) -> bool:
    row = (
        await session.execute(select(CustomPack).where(CustomPack.name == name))
    ).scalars().first()
    if row is None:
        return False
    row.manifest = manifest.model_dump(mode="json")
    row.updated_at = utcnow()
    await session.commit()
    return True


async def delete_custom(session: AsyncSession, name: str) -> bool:
    row = (
        await session.execute(select(CustomPack).where(CustomPack.name == name))
    ).scalars().first()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def _has_install(
    session: AsyncSession, name: str, version: str
) -> bool:
    row = (
        await session.execute(
            select(PackInstall.id).where(
                PackInstall.name == name, PackInstall.version == version
            )
        )
    ).first()
    return row is not None


async def _validate_refs(
    session: AsyncSession,
    principal: Principal,
    manifest: PackManifest,
) -> None:
    tool_refs = list(manifest.tools)
    skill_refs = list(manifest.skills)
    for agent in manifest.agents:
        tool_refs.extend(agent.tools)
        skill_refs.extend(agent.skills)
    tool_refs = list(dict.fromkeys(tool_refs))
    skill_refs = list(dict.fromkeys(skill_refs))
    try:
        await tools_repo.resolve_tool_refs(session, tool_refs)
        await mcp_connections_repo.validate_refs(session, principal, tool_refs)
        await skills_repo.resolve_skill_refs(session, skill_refs)
    except (UnknownRefs, ValueError, PermissionError) as exc:
        raise PackValidationError(str(exc)) from exc

    wanted_subagents = {
        name
        for agent in manifest.agents
        for name in agent.sub_agents
        if name not in {item.slug for item in manifest.agents}
    }
    if wanted_subagents:
        existing = set(
            (
                await session.execute(
                    select(Agent.slug).where(Agent.slug.in_(wanted_subagents))
                )
            ).scalars()
        )
        missing = sorted(wanted_subagents - existing)
        if missing:
            raise PackValidationError(
                "unknown sub-agents: " + ", ".join(missing)
            )


def _agent_values(config: AgentUpsert) -> dict[str, Any]:
    return {
        "name": config.name,
        "description": config.description,
        "system_prompt": config.system_prompt,
        "tools": list(config.tools),
        "skills": list(config.skills),
        "sub_agents": list(config.sub_agents),
        "memory_enabled": bool(config.memory_enabled),
        "llm": dict(config.llm),
        "limits": {**_default_limits(), **config.limits},
    }


async def _existing_agents(
    session: AsyncSession, manifest: PackManifest
) -> dict[str, Agent]:
    slugs = [agent.slug for agent in manifest.agents]
    if not slugs:
        return {}
    rows = (
        await session.execute(select(Agent).where(Agent.slug.in_(slugs)))
    ).scalars()
    return {row.slug: row for row in rows}


def _actions(
    manifest: PackManifest, existing: dict[str, Agent]
) -> list[PackChange]:
    changes: list[PackChange] = []
    for config in manifest.agents:
        row = existing.get(config.slug)
        if row is None:
            changes.append(PackChange(ref=config.slug, action="create"))
            continue
        if row.pack_name != manifest.name:
            raise PackConflict(
                f"agent {config.slug!r} already exists outside pack {manifest.name!r}"
            )
        values = _agent_values(config)
        current = {
            "name": row.name,
            "description": row.description or "",
            "system_prompt": row.system_prompt or "",
            "tools": list(row.tools or []),
            "skills": list(row.skills or []),
            "sub_agents": list(row.sub_agents or []),
            "memory_enabled": bool(row.memory_enabled),
            "llm": dict(row.llm or {}),
            "limits": {**_default_limits(), **(row.limits or {})},
        }
        same = (
            all(current[key] == values[key] for key in values)
            and row.status == "published"
            and row.visibility == "shared"
        )
        changes.append(
            PackChange(ref=config.slug, action="noop" if same else "update")
        )
    return changes


async def _apply(
    session: AsyncSession,
    principal: Principal,
    manifest: PackManifest,
    existing: dict[str, Agent],
) -> None:
    for config in manifest.agents:
        values = _agent_values(config)
        row = existing.get(config.slug)
        if row is None:
            row = Agent(
                slug=config.slug,
                owner_kind=principal.kind,
                owner_id=principal.id,
                tenant_id=principal.tenant_id,
                visibility="shared",
                status="published",
                pack_name=manifest.name,
                pack_version=manifest.version,
                **values,
            )
            session.add(row)
            await session.flush()
        else:
            for field, value in values.items():
                setattr(row, field, value)
            row.visibility = "shared"
            row.status = "published"
            row.pack_name = manifest.name
            row.pack_version = manifest.version
            row.updated_at = utcnow()
        version = await agents_repo.new_version(
            session, row, created_by=principal.id
        )
        row.published_version_id = version.id


async def install(
    session: AsyncSession,
    principal: Principal,
    manifest: PackManifest,
    *,
    dry_run: bool = False,
) -> PackInstallResult:
    if await _has_install(session, manifest.name, manifest.version):
        return PackInstallResult(
            name=manifest.name,
            version=manifest.version,
            dry_run=dry_run,
            already_installed=True,
        )

    await _validate_refs(session, principal, manifest)
    existing = await _existing_agents(session, manifest)
    changes = _actions(manifest, existing)
    if dry_run:
        return PackInstallResult(
            name=manifest.name,
            version=manifest.version,
            dry_run=True,
            changes=changes,
        )

    await _apply(session, principal, manifest, existing)
    session.add(
        PackInstall(
            name=manifest.name,
            version=manifest.version,
            manifest=manifest.model_dump(mode="json"),
            installed_by=principal.id,
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        if await _has_install(session, manifest.name, manifest.version):
            return PackInstallResult(
                name=manifest.name,
                version=manifest.version,
                already_installed=True,
            )
        raise
    return PackInstallResult(
        name=manifest.name,
        version=manifest.version,
        installed=True,
        changes=changes,
    )
