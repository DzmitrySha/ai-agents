"""`GET /v1/catalog`: agents + tools + skills visible to the caller allowlist."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.auth.deps import SessionDep, require_any_scope, require_csrf
from app.auth.principal import Principal, catalog_allowlist
from app.models import Agent, Skill
from app.repos import tools as tools_repo
from app.runtime.models import (
    CatalogAgentItem,
    CatalogOut,
    CatalogSkillItem,
    ToolSpec,
)

router = APIRouter(
    prefix="/v1/catalog", tags=["catalog"], dependencies=[Depends(require_csrf)]
)


@router.get("", response_model=CatalogOut)
async def get_catalog(
    session: SessionDep,
    principal: Annotated[
        Principal,
        Depends(require_any_scope("agents:read", "tools:read", "skills:read")),
    ],
) -> CatalogOut:
    agent_allow = catalog_allowlist(principal, "agent")
    tool_allow = catalog_allowlist(principal, "tool")
    skill_allow = catalog_allowlist(principal, "skill")
    scopes = set(principal.scopes)

    agents: list[CatalogAgentItem] = []
    if "agents:read" in scopes and (agent_allow is None or agent_allow):
        stmt = select(Agent).where(
            Agent.status == "published",
            Agent.visibility == "shared",
            Agent.published_version_id.is_not(None),
        )
        if agent_allow is not None:
            stmt = stmt.where(Agent.slug.in_(sorted(agent_allow)))
        stmt = stmt.order_by(Agent.slug)
        for row in (await session.execute(stmt)).scalars():
            agents.append(
                CatalogAgentItem(
                    slug=row.slug,
                    name=row.name,
                    description=row.description or "",
                )
            )

    tools: list[ToolSpec] = []
    if "tools:read" in scopes and (tool_allow is None or tool_allow):
        for spec in await tools_repo.tool_specs(session):
            name = str(spec["name"])
            if tool_allow is not None and name not in tool_allow:
                continue
            tools.append(ToolSpec(**spec))

    skills: list[CatalogSkillItem] = []
    if "skills:read" in scopes and (skill_allow is None or skill_allow):
        stmt = select(Skill).order_by(Skill.slug)
        if skill_allow is not None:
            stmt = stmt.where(Skill.slug.in_(sorted(skill_allow)))
        for row in (await session.execute(stmt)).scalars():
            skills.append(
                CatalogSkillItem(
                    slug=row.slug,
                    name=row.name,
                    description=row.description or "",
                )
            )

    return CatalogOut(agents=agents, tools=tools, skills=skills)
