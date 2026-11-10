"""MCP client: tools of external Streamable HTTP servers as LangChain tools."""

from __future__ import annotations

import asyncio
import json
import re
from contextlib import AsyncExitStack
from typing import Any

import httpx2
from langchain_core.tools import BaseTool
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic import ConfigDict, Field

from app.agents.url_safety import assert_public_http_url
from app.settings import get_settings

_NAME_SAFE = re.compile(r"[^A-Za-z0-9_-]+")


def describe_error(exc: BaseException) -> str:
    """Unwrap ExceptionGroup/TaskGroup noise down to the first real error."""
    depth = 0
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions and depth < 5:
        exc = exc.exceptions[0]
        depth += 1
    return f"{type(exc).__name__}: {exc}"


def exposed_name(connection: str, tool: str) -> str:
    """Tool name visible to the LLM: safe charset, ≤64 chars."""
    return _NAME_SAFE.sub("_", f"mcp_{connection}_{tool}")[:64]


def _http_client(url: str, headers: dict[str, str], timeout_seconds: float):
    assert_public_http_url(
        url, allowed_hosts=get_settings().mcp_egress_allowlist
    )
    return httpx2.AsyncClient(
        headers={str(key): str(value) for key, value in (headers or {}).items()},
        timeout=httpx2.Timeout(10.0, read=float(timeout_seconds)),
    )


class MCPTool(BaseTool):
    """One remote MCP tool. Async only: the session lives for the whole run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    args_schema: dict[str, Any] = Field(default_factory=dict)
    client: Any = Field(exclude=True)
    remote_name: str
    timeout_seconds: float
    connection_slug: str

    async def _arun(self, **kwargs: Any) -> str:
        try:
            async with asyncio.timeout(self.timeout_seconds):
                result = await self.client.call_tool(self.remote_name, kwargs)
        except Exception as exc:  # noqa: BLE001 - the model gets the error as text
            return f"error: {type(exc).__name__}: {exc}"

        parts = [
            block.text for block in result.content or [] if block.type == "text"
        ]
        text = "\n".join(parts).strip()
        if not text and result.structured_content is not None:
            text = json.dumps(result.structured_content, ensure_ascii=False)
        if result.is_error:
            text = f"error: {text}"
        limit = get_settings().run_tool_output_max_chars
        if len(text) > limit:
            text = text[:limit] + "\n…(truncated)"
        return text

    def _run(self, **kwargs: Any) -> str:
        raise NotImplementedError("MCP tools are async only")


async def list_remote_tools(
    url: str, headers: dict[str, str], timeout_seconds: float
) -> list[dict[str, str]]:
    """`tools/list` of an external server (used by the «Проверить» endpoint)."""
    async with AsyncExitStack() as stack:
        http_client = _http_client(url, headers, timeout_seconds)
        await stack.enter_async_context(http_client)
        client = await stack.enter_async_context(
            Client(streamable_http_client(url, http_client=http_client))
        )
        listed = await client.list_tools()
    return [
        {"name": tool.name, "description": (tool.description or "")[:1024]}
        for tool in listed.tools
    ]


async def build_mcp_tools(
    defs: list[dict[str, Any]], stack: AsyncExitStack
) -> list[BaseTool]:
    """Open one MCP session per connection and wrap the referenced tools."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in defs:
        groups.setdefault(str(item["connection"]), []).append(item)

    tools: list[BaseTool] = []
    for connection, items in groups.items():
        cfg = items[0]
        http_client = _http_client(
            str(cfg["url"]), dict(cfg.get("headers") or {}), float(cfg["timeout_seconds"])
        )
        await stack.enter_async_context(http_client)
        try:
            client = await stack.enter_async_context(
                Client(streamable_http_client(str(cfg["url"]), http_client=http_client))
            )
            listed = {tool.name: tool for tool in (await client.list_tools()).tools}
        except Exception as exc:  # noqa: BLE001 - surface the cause, not the TaskGroup
            raise RuntimeError(
                f"mcp connection failed: {connection}: {describe_error(exc)}"
            ) from exc
        for item in items:
            remote_name = str(item["tool"])
            remote = listed.get(remote_name)
            if remote is None:
                raise RuntimeError(f"mcp tool not found: {connection}:{remote_name}")
            tools.append(
                MCPTool(
                    name=exposed_name(connection, remote_name),
                    description=(remote.description or remote.name or remote_name)[:1024],
                    args_schema=dict(remote.input_schema or {}),
                    client=client,
                    remote_name=remote_name,
                    timeout_seconds=float(cfg["timeout_seconds"]),
                    connection_slug=connection,
                )
            )

    names = [tool.name for tool in tools]
    duplicates = {name for name in names if names.count(name) > 1}
    if duplicates:
        raise RuntimeError(f"duplicate mcp tool name: {', '.join(sorted(duplicates))}")
    return tools
