"""Normalize and validate catalog allowlists (agents / tools / skills)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools import TOOLS
from app.models import Agent, CustomTool, Skill


def normalize_slugs(slugs: list[str] | None) -> list[str]:
    if not slugs:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in slugs:
        slug = str(raw or "").strip()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        out.append(slug)
    return sorted(out)


async def validate_agent_slugs(session: AsyncSession, slugs: list[str]) -> list[str]:
    """Allowlist may only contain published+shared agents."""
    normalized = normalize_slugs(slugs)
    if not normalized:
        return []
    rows = list(
        (
            await session.execute(
                select(Agent).where(
                    Agent.slug.in_(normalized),
                    Agent.status == "published",
                    Agent.visibility == "shared",
                    Agent.published_version_id.is_not(None),
                )
            )
        ).scalars()
    )
    ok = {row.slug for row in rows}
    missing = [slug for slug in normalized if slug not in ok]
    if missing:
        raise ValueError(
            "agent_slugs must be published+shared agents: " + ", ".join(missing)
        )
    return normalized


async def validate_tool_slugs(session: AsyncSession, slugs: list[str]) -> list[str]:
    """Allowlist: builtin names or enabled custom tool slugs."""
    normalized = normalize_slugs(slugs)
    if not normalized:
        return []
    custom = {
        row.slug
        for row in (
            await session.execute(
                select(CustomTool).where(
                    CustomTool.slug.in_(normalized),
                    CustomTool.enabled.is_(True),
                )
            )
        ).scalars()
    }
    ok = set(TOOLS) | custom
    missing = [slug for slug in normalized if slug not in ok]
    if missing:
        raise ValueError(
            "tool_slugs must be builtin or enabled custom tools: " + ", ".join(missing)
        )
    return normalized


async def validate_skill_slugs(session: AsyncSession, slugs: list[str]) -> list[str]:
    """Allowlist: existing skill slugs."""
    normalized = normalize_slugs(slugs)
    if not normalized:
        return []
    rows = list(
        (
            await session.execute(select(Skill).where(Skill.slug.in_(normalized)))
        ).scalars()
    )
    ok = {row.slug for row in rows}
    missing = [slug for slug in normalized if slug not in ok]
    if missing:
        raise ValueError("skill_slugs must be existing skills: " + ", ".join(missing))
    return normalized
