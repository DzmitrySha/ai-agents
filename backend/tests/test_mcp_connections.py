"""MCP connections (inward): CRUD, ref validation, probe, tool wrapper, run wiring."""

from __future__ import annotations

import asyncio

import pytest

from tests.conftest import AUTH

CONNECTION = {
    "slug": "docs",
    "name": "Docs",
    "description": "Корпоративный поиск",
    "url": "https://mcp.test/mcp",
    "headers": {"Authorization": "Bearer secret", "X-Tenant": "ai-agents"},
    "timeout_seconds": 15,
    "enabled": True,
}


def _agent(slug: str, tools: list[str]) -> dict:
    return {
        "slug": slug,
        "name": slug,
        "description": "uses mcp",
        "kind": "preset",
        "system_prompt": "You are a demo.",
        "tools": tools,
        "limits": {"max_steps": 4, "timeout_seconds": 30},
    }


def test_connection_crud_hides_headers(client, login):
    headers = login("u1")

    created = client.post("/v1/mcp-connections", json=CONNECTION, headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["slug"] == "docs"
    assert body["header_names"] == ["Authorization", "X-Tenant"]
    assert "Bearer secret" not in created.text
    assert body["owner"]["kind"] == "user"
    assert body["tools_cache"] == []

    listed = client.get("/v1/mcp-connections", headers=headers).json()
    assert listed["total"] == 1
    assert listed["items"][0]["header_names"] == ["Authorization", "X-Tenant"]

    duplicate = client.post("/v1/mcp-connections", json=CONNECTION, headers=headers)
    assert duplicate.status_code == 409

    patched = client.patch(
        "/v1/mcp-connections/docs", json={"timeout_seconds": 45}, headers=headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["timeout_seconds"] == 45

    deleted = client.delete("/v1/mcp-connections/docs", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json() == {"slug": "docs", "detached_agents": []}
    assert client.get("/v1/mcp-connections/docs", headers=headers).status_code == 404


def test_agent_refs_are_validated(client, login):
    headers = login("u1")
    assert (
        client.post("/v1/mcp-connections", json=CONNECTION, headers=headers).status_code
        == 201
    )

    ok = client.post("/v1/agents", json=_agent("with-mcp", ["mcp:docs:search"]), headers=headers)
    assert ok.status_code == 201, ok.text
    assert ok.json()["tools"] == ["mcp:docs:search"]

    missing = client.post(
        "/v1/agents", json=_agent("no-conn", ["mcp:missing:search"]), headers=headers
    )
    assert missing.status_code == 422, missing.text
    assert "unknown mcp connections" in missing.text

    malformed = client.post(
        "/v1/agents", json=_agent("bad-ref", ["mcp:docs"]), headers=headers
    )
    assert malformed.status_code == 422, malformed.text

    other = login("u2")
    foreign = client.post(
        "/v1/agents", json=_agent("foreign", ["mcp:docs:search"]), headers=other
    )
    assert foreign.status_code == 403, foreign.text

    headers = login("u1")
    disabled = client.patch(
        "/v1/mcp-connections/docs", json={"enabled": False}, headers=headers
    )
    assert disabled.status_code == 200
    blocked = client.patch(
        "/v1/agents/with-mcp", json={"tools": ["mcp:docs:search"]}, headers=headers
    )
    assert blocked.status_code == 422, blocked.text
    assert "disabled" in blocked.text


def test_delete_detaches_refs_from_agents(client, login):
    headers = login("u1")
    assert (
        client.post("/v1/mcp-connections", json=CONNECTION, headers=headers).status_code
        == 201
    )
    created = client.post(
        "/v1/agents",
        json=_agent("detach-me", ["calculator", "mcp:docs:search"]),
        headers=headers,
    )
    assert created.status_code == 201, created.text

    deleted = client.delete("/v1/mcp-connections/docs", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["detached_agents"] == ["detach-me"]

    agent = client.get("/v1/agents/detach-me", headers=headers).json()
    assert agent["tools"] == ["calculator"]


def test_probe_caches_tools_and_reports_errors(client, login, monkeypatch):
    from app.agents import mcp_client

    headers = login("u1")
    assert (
        client.post("/v1/mcp-connections", json=CONNECTION, headers=headers).status_code
        == 201
    )

    async def _ok(url, conn_headers, timeout_seconds):
        assert url == CONNECTION["url"]
        assert conn_headers["Authorization"] == "Bearer secret"
        return [{"name": "search", "description": "Поиск"}]

    monkeypatch.setattr(mcp_client, "list_remote_tools", _ok)
    tested = client.post("/v1/mcp-connections/docs/test", headers=headers)
    assert tested.status_code == 200, tested.text
    assert tested.json() == {
        "ok": True,
        "tools": [{"name": "search", "description": "Поиск"}],
        "error": None,
    }

    cached = client.get("/v1/mcp-connections/docs", headers=headers).json()
    assert cached["tools_cache"] == [{"name": "search", "description": "Поиск"}]
    assert cached["tools_cached_at"] is not None

    async def _boom(url, conn_headers, timeout_seconds):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(mcp_client, "list_remote_tools", _boom)
    failed = client.post("/v1/mcp-connections/docs/test", headers=headers).json()
    assert failed["ok"] is False
    assert failed["tools"] == []
    assert failed["error"].startswith("error:")


def test_mcp_tool_wraps_results(monkeypatch):
    from mcp.types import CallToolResult, TextContent

    from app.agents.mcp_client import MCPTool, exposed_name

    class _Client:
        def __init__(self, result):
            self.result = result

        async def call_tool(self, name, arguments):
            assert name == "search"
            return self.result

    def _tool(result) -> MCPTool:
        return MCPTool(
            name=exposed_name("docs", "search"),
            description="search",
            args_schema={"type": "object"},
            client=_Client(result),
            remote_name="search",
            timeout_seconds=5.0,
            connection_slug="docs",
        )

    assert exposed_name("docs", "search") == "mcp_docs_search"

    ok = asyncio.run(
        _tool(CallToolResult(content=[TextContent(type="text", text="out")])).ainvoke({})
    )
    assert ok == "out"

    failed = asyncio.run(
        _tool(
            CallToolResult(content=[TextContent(type="text", text="boom")], is_error=True)
        ).ainvoke({})
    )
    assert failed == "error: boom"

    long = asyncio.run(
        _tool(CallToolResult(content=[TextContent(type="text", text="y" * 9000)])).ainvoke({})
    )
    assert long.startswith("y" * 100)
    assert long.endswith("…(truncated)")
    assert len(long) < 8100


def test_run_resolves_mcp_defs(client, login, monkeypatch):
    from app.agents.events import AgentEvent
    from app.runtime import manager as manager_module

    headers = login("u1")
    assert (
        client.post("/v1/mcp-connections", json=CONNECTION, headers=headers).status_code
        == 201
    )
    created = client.post(
        "/v1/agents", json=_agent("mcp-run", ["mcp:docs:search"]), headers=headers
    )
    assert created.status_code == 201, created.text
    published = client.post(
        "/v1/agents/mcp-run/publish", json={"visibility": "private"}, headers=headers
    )
    assert published.status_code == 200, published.text

    captured: dict = {}

    async def _fake_stream(agent, prompt, run_override, max_steps):
        captured["agent"] = agent
        yield AgentEvent("message.delta", {"delta": "done"})

    monkeypatch.setattr(manager_module, "stream_agent", _fake_stream)

    run = client.post(
        "/v1/runs", json={"agent_id": "mcp-run", "input": "hi"}, headers=headers
    )
    assert run.status_code == 201, run.text
    run_id = run.json()["run_id"]

    async def _wait() -> None:
        await client.app.state.run_manager.wait_completed(run_id)

    client.portal.call(_wait)

    defs = captured["agent"].mcp_defs
    assert len(defs) == 1
    assert defs[0]["connection"] == "docs"
    assert defs[0]["tool"] == "search"
    assert defs[0]["url"] == CONNECTION["url"]
    assert defs[0]["headers"]["Authorization"] == "Bearer secret"
    assert defs[0]["timeout_seconds"] == 15
    assert captured["agent"].tool_defs == []

    finished = client.get(f"/v1/runs/{run_id}", headers=headers).json()
    assert finished["status"] == "succeeded"
    assert finished["output"] == "done"

    harness = client.get(f"/v1/runs/{run_id}/harness", headers=headers).json()
    assert "Bearer secret" not in str(harness)
    assert harness["snapshot"]["mcp"] == [
        {
            "ref": "mcp:docs:search",
            "connection": "docs",
            "url": CONNECTION["url"],
            "tool": "search",
            "timeout_seconds": 15,
            "header_names": ["Authorization", "X-Tenant"],
        }
    ]
