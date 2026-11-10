"""MCP server: allowlisted agents, atomic tools, and skill fetch over `/mcp`."""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server import Server, ServerRequestContext
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool
from pydantic import AnyHttpUrl
from sqlalchemy import select
from starlette.applications import Starlette

from app.auth.principal import READER_SCOPES, Principal
from app.models import Agent, McpServer
from app.repos import mcp_servers as mcp_servers_repo
from app.repos import skills as skills_repo
from app.repos import tools as tools_repo
from app.repos.runs import get_run_row
from app.runtime.manager import QueueFull
from app.runtime.models import CreateRunRequest
from app.settings import Settings

PROMPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string", "title": "Prompt", "description": "Запрос агенту"}
    },
    "required": ["prompt"],
    "additionalProperties": False,
}
GET_SKILL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "slug": {
            "type": "string",
            "title": "Slug",
            "description": "Slug навыка из allowlist ключа",
        }
    },
    "required": ["slug"],
    "additionalProperties": False,
}
MCP_SCOPE = "mcp"
MCP_PATH = "/mcp"
TOOL_PREFIX = "tool__"
GET_SKILL_NAME = "get_skill"


def _error(message: str) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=f"error: {message}")], is_error=True
    )


def _tool_from_agent(row: Agent) -> Tool:
    return Tool(
        name=row.slug,
        description=(f"{row.name} — {row.description}".strip(" —") or row.slug)[:1024],
        input_schema=PROMPT_SCHEMA,
    )


def _tool_from_spec(spec: dict[str, Any]) -> Tool:
    name = str(spec["name"])
    params = spec.get("parameters") or {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    if not isinstance(params, dict):
        params = {"type": "object", "properties": {}}
    return Tool(
        name=f"{TOOL_PREFIX}{name}",
        description=(str(spec.get("description") or name))[:1024],
        input_schema=params,
    )


def _get_skill_tool() -> Tool:
    return Tool(
        name=GET_SKILL_NAME,
        description="Получить текст SKILL.md по slug из allowlist ключа",
        input_schema=GET_SKILL_SCHEMA,
    )


class McpTokenVerifier:
    """Structural `TokenVerifier`: `mcp_servers.key_hash` → `AccessToken`."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def verify_token(self, token: str) -> AccessToken | None:
        async with self._session_factory() as session:
            row = await mcp_servers_repo.authenticate(session, token)
        if row is None:
            return None
        return AccessToken(
            token=token,
            client_id=row.slug,
            scopes=[MCP_SCOPE],
            claims={"mcp_server_id": row.id},
        )


def build_mcp_server(*, session_factory, manager, settings: Settings) -> Server:
    async def _load_key(session) -> McpServer | None:
        token = get_access_token()
        if token is None or not token.client_id:
            return None
        return await mcp_servers_repo.get_server(session, token.client_id)

    async def on_list_tools(
        _ctx: ServerRequestContext, _params: Any
    ) -> ListToolsResult:
        tools: list[Tool] = []
        async with session_factory() as session:
            key = await _load_key(session)
            if key is None or not key.enabled:
                return ListToolsResult(tools=[])

            agent_allow = [
                str(slug) for slug in (key.agent_slugs or []) if str(slug).strip()
            ]
            if agent_allow:
                stmt = (
                    select(Agent)
                    .where(
                        Agent.slug.in_(agent_allow),
                        Agent.status == "published",
                        Agent.visibility == "shared",
                        Agent.published_version_id.is_not(None),
                    )
                    .order_by(Agent.slug)
                )
                for row in (await session.execute(stmt)).scalars():
                    tools.append(_tool_from_agent(row))

            tool_allow = {
                str(slug) for slug in (key.tool_slugs or []) if str(slug).strip()
            }
            if tool_allow:
                for spec in await tools_repo.tool_specs(session):
                    if str(spec["name"]) in tool_allow:
                        tools.append(_tool_from_spec(spec))

            skill_allow = [
                str(slug) for slug in (key.skill_slugs or []) if str(slug).strip()
            ]
            if skill_allow:
                tools.append(_get_skill_tool())

        return ListToolsResult(tools=tools)

    async def _call_agent(
        *, agent_slug: str, prompt: str, server_id: str
    ) -> CallToolResult:
        principal = Principal(kind="mcp", id=server_id, scopes=READER_SCOPES)
        request = CreateRunRequest(
            agent_id=agent_slug, input=prompt, metadata={"mcp_server": server_id}
        )
        try:
            out = await manager.create_run(session_factory, principal, request)
        except KeyError:
            return _error(f"unknown agent: {agent_slug}")
        except QueueFull as exc:
            return _error(str(exc))
        except ValueError as exc:
            return _error(str(exc))

        try:
            async with asyncio.timeout(float(settings.run_timeout_cap_seconds) + 30):
                await manager.wait_completed(out.run_id)
        except TimeoutError:
            await manager.cancel_run(session_factory, out.run_id, principal)
            return _error("run timed out")
        except asyncio.CancelledError:
            await manager.cancel_run(session_factory, out.run_id, principal)
            raise

        async with session_factory() as session:
            row = await get_run_row(session, out.run_id)
        text = (row.output or row.error or "") if row is not None else ""
        failed = row is None or row.status != "succeeded"
        return CallToolResult(
            content=[TextContent(type="text", text=text or "error: empty run output")],
            is_error=failed,
        )

    async def on_call_tool(
        _ctx: ServerRequestContext, params: Any
    ) -> CallToolResult:
        arguments = dict(params.arguments or {})
        name = str(params.name or "")

        async with session_factory() as session:
            key = await _load_key(session)
            if key is None or not key.enabled:
                return _error(f"unknown tool: {name}")

            agent_allow = {
                str(slug) for slug in (key.agent_slugs or []) if str(slug).strip()
            }
            tool_allow = {
                str(slug) for slug in (key.tool_slugs or []) if str(slug).strip()
            }
            skill_allow = {
                str(slug) for slug in (key.skill_slugs or []) if str(slug).strip()
            }

            if name == GET_SKILL_NAME:
                slug = arguments.get("slug")
                if not isinstance(slug, str) or not slug.strip():
                    return _error("slug is required")
                slug = slug.strip()
                if slug not in skill_allow:
                    return _error(f"unknown skill: {slug}")
                skill = await skills_repo.get_skill(session, slug)
                if skill is None:
                    return _error(f"unknown skill: {slug}")
                return CallToolResult(
                    content=[TextContent(type="text", text=skill.content or "")],
                    is_error=False,
                )

            if name.startswith(TOOL_PREFIX):
                tool_slug = name[len(TOOL_PREFIX) :]
                if tool_slug not in tool_allow:
                    return _error(f"unknown tool: {tool_slug}")
                try:
                    result = await tools_repo.invoke_by_name(
                        session, tool_slug, arguments
                    )
                except KeyError:
                    return _error(f"unknown tool: {tool_slug}")
                return CallToolResult(
                    content=[TextContent(type="text", text=result.output or "")],
                    is_error=not result.ok,
                )

            if name not in agent_allow:
                return _error(f"unknown agent: {name}")

        prompt = arguments.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return _error("prompt is required")

        token = get_access_token()
        server_id = token.client_id if token is not None else "in-process"
        return await _call_agent(
            agent_slug=name, prompt=prompt, server_id=server_id
        )

    return Server(
        name=settings.app_name,
        version="0.1.0",
        instructions=(
            "Каталог ai-agents по allowlist ключа: агенты (prompt), "
            f"атомарные tools (`{TOOL_PREFIX}<slug>` без LLM), "
            f"`{GET_SKILL_NAME}` (текст навыка)."
        ),
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


def build_mcp_asgi(mcp_server: Server, settings: Settings, session_factory) -> Starlette:
    resource = settings.public_url.rstrip("/") + MCP_PATH
    return mcp_server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            # Clients send Host matching the URL they use (FQDN / localhost /
            # host.docker.internal). No Host spoofing in MCP clients.
            allowed_hosts=settings.mcp_allowed_hosts,
            allowed_origins=[settings.public_url.rstrip("/")],
        ),
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(settings.public_url),
            resource_server_url=AnyHttpUrl(resource),
            required_scopes=[MCP_SCOPE],
            validate_token_resource=False,
        ),
        token_verifier=McpTokenVerifier(session_factory),
    )
