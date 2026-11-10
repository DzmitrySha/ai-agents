"""MCP server (outward): admin keys, allowlist, tools/list, tools/call, HTTP auth."""

from __future__ import annotations

from mcp.server.auth.provider import AccessToken

from tests.conftest import AUTH

PROMPT = {"prompt": "hi"}


def _agent(slug: str, *, prompt: str = "You are a demo.") -> dict:
    return {
        "slug": slug,
        "name": slug,
        "description": f"{slug} agent",
        "kind": "preset",
        "system_prompt": prompt,
        "tools": [],
        "limits": {"max_steps": 4, "timeout_seconds": 30},
    }


def _published_preset(client, slug: str, *, visibility: str = "shared") -> None:
    created = client.post("/v1/agents", json=_agent(slug), headers=AUTH)
    assert created.status_code == 201, created.text
    published = client.post(
        f"/v1/agents/{slug}/publish", json={"visibility": visibility}, headers=AUTH
    )
    assert published.status_code == 200, published.text


def _create_key(
    client,
    login,
    *,
    slug: str = "cursor",
    agent_slugs: list[str] | None = None,
    tool_slugs: list[str] | None = None,
    skill_slugs: list[str] | None = None,
):
    headers = login("root", is_superadmin=True)
    body = {"slug": slug, "name": slug.title(), "description": "test"}
    if agent_slugs is not None:
        body["agent_slugs"] = agent_slugs
    if tool_slugs is not None:
        body["tool_slugs"] = tool_slugs
    if skill_slugs is not None:
        body["skill_slugs"] = skill_slugs
    created = client.post("/api/admin/mcp-servers", json=body, headers=headers)
    assert created.status_code == 201, created.text
    return created.json(), headers


def _auth_as(monkeypatch, slug: str) -> None:
    monkeypatch.setattr(
        "app.agents.mcp_server.get_access_token",
        lambda: AccessToken(
            token="test",
            client_id=slug,
            scopes=["mcp"],
            claims={},
        ),
    )


def test_admin_mcp_server_crud(client, login):
    _published_preset(client, "demo-chat")
    headers = login("root", is_superadmin=True)
    created = client.post(
        "/api/admin/mcp-servers",
        json={
            "slug": "cursor",
            "name": "Cursor",
            "description": "ноутбук",
            "agent_slugs": ["demo-chat"],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["api_key"].startswith("mcp-ag-")
    assert body["url"].endswith("/mcp")
    assert body["enabled"] is True
    assert body["agent_slugs"] == ["demo-chat"]
    assert body["tool_slugs"] == []
    assert body["skill_slugs"] == []

    listed = client.get("/api/admin/mcp-servers", headers=headers).json()
    assert listed["total"] == 1
    assert "api_key" not in listed["items"][0]
    assert listed["items"][0]["agent_slugs"] == ["demo-chat"]

    empty_default = client.post(
        "/api/admin/mcp-servers",
        json={"slug": "empty-key", "name": "Empty"},
        headers=headers,
    )
    assert empty_default.status_code == 201, empty_default.text
    assert empty_default.json()["agent_slugs"] == []
    assert empty_default.json()["tool_slugs"] == []
    assert empty_default.json()["skill_slugs"] == []

    duplicate = client.post(
        "/api/admin/mcp-servers", json={"slug": "cursor", "name": "Again"}, headers=headers
    )
    assert duplicate.status_code == 409

    disabled = client.patch(
        "/api/admin/mcp-servers/cursor", json={"enabled": False}, headers=headers
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert "api_key" not in disabled.json()

    rotated = client.patch(
        "/api/admin/mcp-servers/cursor", json={"rotate_key": True}, headers=headers
    )
    assert rotated.status_code == 200
    assert rotated.json()["api_key"].startswith("mcp-ag-")
    assert rotated.json()["api_key"] != body["api_key"]

    assert (
        client.delete("/api/admin/mcp-servers/cursor", headers=headers).status_code == 204
    )
    assert client.delete("/api/admin/mcp-servers/cursor", headers=headers).status_code == 404


def test_admin_mcp_server_requires_superadmin(client, login):
    headers = login("plain", is_superadmin=False)
    assert (
        client.get("/api/admin/mcp-servers", headers=headers).status_code == 403
    )
    assert (
        client.post(
            "/api/admin/mcp-servers", json={"slug": "x1", "name": "X"}, headers=headers
        ).status_code
        == 403
    )


def test_agent_slugs_must_be_published_shared(client, login):
    _published_preset(client, "demo-chat")
    _published_preset(client, "demo-private", visibility="private")
    headers = login("root", is_superadmin=True)

    bad_private = client.post(
        "/api/admin/mcp-servers",
        json={"slug": "k1", "name": "K1", "agent_slugs": ["demo-private"]},
        headers=headers,
    )
    assert bad_private.status_code == 422

    bad_missing = client.post(
        "/api/admin/mcp-servers",
        json={"slug": "k2", "name": "K2", "agent_slugs": ["nope"]},
        headers=headers,
    )
    assert bad_missing.status_code == 422

    ok = client.post(
        "/api/admin/mcp-servers",
        json={"slug": "k3", "name": "K3", "agent_slugs": ["demo-chat"]},
        headers=headers,
    )
    assert ok.status_code == 201, ok.text

    patch_bad = client.patch(
        "/api/admin/mcp-servers/k3",
        json={"agent_slugs": ["demo-private"]},
        headers=headers,
    )
    assert patch_bad.status_code == 422


def test_list_tools_respects_allowlist(client, fake_graph, login, monkeypatch):
    _published_preset(client, "demo-chat")
    _published_preset(client, "demo-other")
    _published_preset(client, "demo-private", visibility="private")

    empty_key, _ = _create_key(client, login, slug="empty", agent_slugs=[])
    _auth_as(monkeypatch, "empty")

    async def _list() -> list[str]:
        from mcp import Client

        async with Client(client.app.state.mcp_server) as session:
            result = await session.list_tools()
        return [tool.name for tool in result.tools]

    assert client.portal.call(_list) == []

    _create_key(client, login, slug="cursor", agent_slugs=["demo-chat"])
    _auth_as(monkeypatch, "cursor")
    assert client.portal.call(_list) == ["demo-chat"]

    # Without token → empty (no global shared dump).
    monkeypatch.setattr("app.agents.mcp_server.get_access_token", lambda: None)
    assert client.portal.call(_list) == []
    assert empty_key["agent_slugs"] == []


def test_call_tool_runs_agent_as_mcp_principal(client, fake_graph, run_db, login, monkeypatch):
    _published_preset(client, "demo-chat")
    _published_preset(client, "demo-other")
    _create_key(client, login, slug="cursor", agent_slugs=["demo-chat"])
    _auth_as(monkeypatch, "cursor")

    async def _call(name: str, arguments: dict):
        from mcp import Client

        async with Client(client.app.state.mcp_server) as session:
            return await session.call_tool(name, arguments)

    result = client.portal.call(_call, "demo-chat", PROMPT)
    assert result.is_error is False, result
    assert result.content[0].text == "hello world"

    async def _runs() -> list[tuple[str, str]]:
        from sqlalchemy import select

        from app.db import get_session_factory
        from app.models import RunRow

        async with get_session_factory()() as session:
            rows = await session.execute(
                select(RunRow.principal_kind, RunRow.principal_id)
            )
            return [(row[0], row[1]) for row in rows]

    principals = run_db(_runs)
    assert ("mcp", "cursor") in principals

    denied = client.portal.call(_call, "demo-other", PROMPT)
    assert denied.is_error is True
    assert "unknown agent" in denied.content[0].text

    missing = client.portal.call(_call, "nope", PROMPT)
    assert missing.is_error is True
    assert "unknown agent" in missing.content[0].text

    empty = client.portal.call(_call, "demo-chat", {})
    assert empty.is_error is True
    assert "prompt is required" in empty.content[0].text


def test_mcp_atomic_tool_and_get_skill(client, fake_graph, login, monkeypatch):
    admin = login("root", is_superadmin=True)
    skill = client.post(
        "/v1/skills",
        headers=admin,
        json={
            "name": "Brief",
            "slug": "brief-reply",
            "description": "short",
            "content": "# Brief\nBe short.\n",
        },
    )
    assert skill.status_code == 201, skill.text

    _create_key(
        client,
        login,
        slug="hybrid",
        agent_slugs=[],
        tool_slugs=["calculator"],
        skill_slugs=["brief-reply"],
    )
    _auth_as(monkeypatch, "hybrid")

    async def _list() -> list[str]:
        from mcp import Client

        async with Client(client.app.state.mcp_server) as session:
            result = await session.list_tools()
        return sorted(tool.name for tool in result.tools)

    names = client.portal.call(_list)
    assert names == ["get_skill", "tool__calculator"]

    async def _call(name: str, arguments: dict):
        from mcp import Client

        async with Client(client.app.state.mcp_server) as session:
            return await session.call_tool(name, arguments)

    calc = client.portal.call(_call, "tool__calculator", {"expression": "3*3"})
    assert calc.is_error is False, calc
    assert calc.content[0].text == "9"

    text = client.portal.call(_call, "get_skill", {"slug": "brief-reply"})
    assert text.is_error is False, text
    assert "Be short" in text.content[0].text

    denied = client.portal.call(_call, "tool__now", {})
    assert denied.is_error is True


def test_http_endpoint_requires_bearer_and_rotates(client, login):
    headers = login("root", is_superadmin=True)
    created = client.post(
        "/api/admin/mcp-servers", json={"slug": "cursor", "name": "Cursor"}, headers=headers
    )
    assert created.status_code == 201, created.text
    api_key = created.json()["api_key"]

    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "t", "version": "1"},
        },
    }
    accept = {"Accept": "application/json, text/event-stream"}

    anonymous = client.post("/mcp", json=init, headers=accept)
    assert anonymous.status_code == 401

    authorized = client.post(
        "/mcp", json=init, headers={**accept, "Authorization": f"Bearer {api_key}"}
    )
    assert authorized.status_code not in (401, 403), authorized.text

    rotated = client.patch(
        "/api/admin/mcp-servers/cursor", json={"rotate_key": True}, headers=headers
    ).json()["api_key"]
    stale = client.post(
        "/mcp", json=init, headers={**accept, "Authorization": f"Bearer {api_key}"}
    )
    assert stale.status_code == 401
    fresh = client.post(
        "/mcp", json=init, headers={**accept, "Authorization": f"Bearer {rotated}"}
    )
    assert fresh.status_code not in (401, 403), fresh.text
