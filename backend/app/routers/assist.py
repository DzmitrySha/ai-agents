"""`/v1/assist`: LLM autofill for the agent/tool forms.

Suggestions only — nothing is persisted. The model sees the real catalogue of
builtin/custom tools and imported skills, and its answer is normalized against
that catalogue before it reaches the UI.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.assist import (
    AGENT_SYSTEM,
    SKILL_SYSTEM,
    TOOL_SYSTEM,
    AssistError,
    agent_prompt,
    chat_reply,
    complete_json,
    normalize_skill,
    normalize_agent,
    normalize_tool,
    skill_prompt,
    tool_prompt,
)
from app.agents.assist import (
    _skills_context as skills_context,
    _tools_context as tools_context,
)
from app.auth.deps import SessionDep, require_csrf, require_scope
from app.auth.principal import Principal
from app.models import Agent
from app.repos import skills as skills_repo
from app.repos import tools as tools_repo
from app.runtime.models import (
    AgentSuggestion,
    AssistAgentRequest,
    AssistChatRequest,
    AssistChatResponse,
    AssistSkillRequest,
    AssistToolRequest,
    SkillSuggestion,
    ToolSuggestion,
)

router = APIRouter(
    prefix="/v1/assist", tags=["assist"], dependencies=[Depends(require_csrf)]
)


async def _used_agent_slugs(session: AsyncSession) -> list[str]:
    rows = await session.execute(select(Agent.slug).where(Agent.status != "archived"))
    return [str(row[0]) for row in rows]


async def _tool_catalogue(
    session: AsyncSession,
) -> tuple[list[dict], list[str]]:
    """Visible tools for the prompt + every taken slug (incl. disabled ones)."""
    specs = await tools_repo.tool_specs(session)
    rows = await tools_repo.list_tools(session, include_disabled=True)
    taken = [str(spec["name"]) for spec in specs] + [row.slug for row in rows]
    return specs, sorted(set(taken))


@router.post("/agent", response_model=AgentSuggestion)
async def suggest_agent(
    payload: AssistAgentRequest,
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_scope("agents:write"))],
) -> AgentSuggestion:
    specs, taken_tools = await _tool_catalogue(session)
    skills = await skills_repo.list_skills(session)
    used_slugs = await _used_agent_slugs(session)
    try:
        raw = await complete_json(
            AGENT_SYSTEM,
            agent_prompt(payload.description, specs, skills, used_slugs),
            payload.llm,
        )
    except AssistError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return AgentSuggestion(
        **normalize_agent(
            raw,
            known_tools=[str(spec["name"]) for spec in specs],
            reserved_tools=taken_tools,
            known_skills=[skill.slug for skill in skills],
            used_slugs=used_slugs,
        )
    )


@router.post("/tool", response_model=ToolSuggestion)
async def suggest_tool(
    payload: AssistToolRequest,
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_scope("agents:write"))],
) -> ToolSuggestion:
    _specs, taken_tools = await _tool_catalogue(session)
    try:
        raw = await complete_json(
            TOOL_SYSTEM, tool_prompt(payload.description), payload.llm
        )
    except AssistError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return ToolSuggestion(**normalize_tool(raw, used_slugs=taken_tools))


async def _service_context(session: AsyncSession) -> str:
    """Каталог + карта UI для advice/review: slug и краткие описания, не только имена."""
    from app.repos import mcp_connections as mcp_connections_repo
    from app.repos import mcp_servers as mcp_servers_repo

    specs, _taken = await _tool_catalogue(session)
    skills = await skills_repo.list_skills(session)
    agents = list((await session.execute(select(Agent))).scalars())
    connections = await mcp_connections_repo.list_connections(session)
    servers = await mcp_servers_repo.list_servers(session)
    agent_lines = []
    for agent in sorted(agents, key=lambda item: item.slug)[:40]:
        desc = " ".join((agent.description or "").split())
        if len(desc) > 100:
            desc = desc[:99] + "…"
        suffix = f" — {desc}" if desc else ""
        agent_lines.append(
            f"- {agent.slug} ({agent.status}/{agent.visibility}): {agent.name}{suffix}"
        )
    connection_lines = []
    for conn in connections[:20]:
        connection_lines.append(
            f"- {conn.slug}: {conn.name}"
            + (f" — {conn.url}" if getattr(conn, "url", None) else "")
        )
    server_lines = []
    for server in servers[:20]:
        allow = ",".join(server.agent_slugs or []) or "—"
        server_lines.append(f"- {server.slug}: {server.name} (agents: {allow})")
    lines = [
        "Установленные инструменты (каталог /tools):\n" + tools_context(specs),
        "Установленные навыки (каталог /skills):\n" + skills_context(skills),
        "Агенты:\n" + ("\n".join(agent_lines) or "нет"),
        "MCP-подключения (внутрь):\n" + ("\n".join(connection_lines) or "нет"),
        "MCP-серверы (ключи наружу):\n" + ("\n".join(server_lines) or "нет"),
        "Published+shared кандидаты в allowlist MCP-ключа: "
        + (
            ", ".join(
                [
                    agent.slug
                    for agent in sorted(agents, key=lambda item: item.slug)
                    if agent.status == "published" and agent.visibility == "shared"
                ][:40]
            )
            or "нет"
        ),
        "Подсказка MCP-server: назначь agent_slugs (published+shared); пустой список = "
        "tools/list пустой. После create клиент получает JSON "
        '{"mcpServers":{"ai-agents":{"url":"<PUBLIC>/mcp","headers":{"Authorization":"Bearer mcp-ag-…"}}}}; '
        "ключ один раз, rotate выдаёт новый.",
        "Маршруты UI: /agents — агенты, /runs — запуски, /tools — инструменты, "
        "/skills — навыки (SKILL.md), "
        "/integrations/mcp — MCP (ключи наружу и подключения внутрь), /stats — обзор, "
        "/admin/users — пользователи и роли, /admin/llm — провайдеры LLM, "
        "/admin/keys — ключи сервиса.",
    ]
    return "\n".join(lines)


@router.post("/chat", response_model=AssistChatResponse)
async def chat(
    payload: AssistChatRequest,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("agents:read"))],
) -> AssistChatResponse:
    """Чат-ассистент по всему сервису: подсказать, проверить, предложить тест, заполнить форму."""
    if payload.mode == "form" and not (principal.is_superadmin or "agents:write" in principal.scopes):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Заполнение форм требует скоупа agents:write",
        )
    try:
        result = await chat_reply(
            mode=payload.mode,
            target=payload.target,
            message=payload.message,
            current=payload.current,
            history=[item.model_dump() for item in payload.history],
            context=await _service_context(session),
            llm=payload.llm,
        )
    except AssistError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return AssistChatResponse(**result)


@router.post("/skill", response_model=SkillSuggestion)
async def suggest_skill(
    payload: AssistSkillRequest,
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_scope("agents:write"))],
) -> SkillSuggestion:
    skills = await skills_repo.list_skills(session)
    used = [skill.slug for skill in skills]
    try:
        raw = await complete_json(
            SKILL_SYSTEM, skill_prompt(payload.description, used), payload.llm
        )
    except AssistError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return SkillSuggestion(**normalize_skill(raw, used_slugs=used))
