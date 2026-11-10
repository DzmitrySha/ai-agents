"""No-code custom HTTP tools: CRUD, templating, test-run, agent wiring."""

from __future__ import annotations

import json
import socket

import httpx

from tests.conftest import AUTH

TOOL = {
    "slug": "weather",
    "name": "Weather",
    "description": "Fetch a weather forecast",
    "method": "POST",
    "url": "https://example.com/geo/{city}",
    "headers": {"X-Key": "secret"},
    "query": {"q": "{q}"},
    "body_template": '{"city": "{city}", "days": {days}}',
    "parameters": [
        {"name": "city", "type": "string", "required": True},
        {"name": "q", "type": "string", "required": True},
        {"name": "days", "type": "integer", "required": False},
    ],
    "timeout_seconds": 5,
}


def _mock_http(monkeypatch, handler) -> None:
    from app.agents import custom_http

    real_client = httpx.AsyncClient

    def factory(**kwargs):
        kwargs.pop("follow_redirects", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(custom_http.httpx, "AsyncClient", factory)

    def fake_getaddrinfo(host, port, *args, **kwargs):
        del port, args, kwargs
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


def test_custom_tool_crud_and_registry(client):
    created = client.post("/v1/tools", json=TOOL, headers=AUTH)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["slug"] == "weather"
    assert body["owner"]["kind"] == "service"
    assert body["parameters"][0]["name"] == "city"
    assert body["header_names"] == ["X-Key"]
    assert "headers" not in body
    assert "secret" not in created.text

    listed = client.get("/v1/tools", headers=AUTH).json()
    weather = next(item for item in listed if item["name"] == "weather")
    assert weather["source"] == "custom"
    assert weather["parameters"]["properties"]["city"]["type"] == "string"
    assert set(weather["parameters"]["required"]) == {"city", "q"}

    detail = client.get("/v1/tools/weather", headers=AUTH)
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["method"] == "POST"
    assert detail_body["header_names"] == ["X-Key"]
    assert "headers" not in detail_body
    assert "secret" not in detail.text

    custom = client.get("/v1/tools/custom", headers=AUTH).json()
    assert custom["total"] == 1
    assert custom["items"][0]["url"] == TOOL["url"]
    assert custom["items"][0]["header_names"] == ["X-Key"]
    assert "headers" not in custom["items"][0]


def test_custom_tool_patch_keeps_headers_when_omitted(client, monkeypatch):
    assert client.post("/v1/tools", json=TOOL, headers=AUTH).status_code == 201
    patched = client.patch(
        "/v1/tools/weather",
        json={"name": "Weather 2"},
        headers=AUTH,
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Weather 2"
    assert patched.json()["header_names"] == ["X-Key"]

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"ok": True})

    _mock_http(monkeypatch, handler)
    tested = client.post(
        "/v1/tools/weather/test",
        headers=AUTH,
        json={"params": {"city": "Minsk", "q": "x", "days": 1}},
    )
    assert tested.status_code == 200
    assert captured["headers"]["x-key"] == "secret"


def test_reserved_and_duplicate_slugs(client):
    reserved = client.post("/v1/tools", json={**TOOL, "slug": "calculator"}, headers=AUTH)
    assert reserved.status_code == 409

    assert client.post("/v1/tools", json=TOOL, headers=AUTH).status_code == 201
    duplicate = client.post("/v1/tools", json=TOOL, headers=AUTH)
    assert duplicate.status_code == 409


def test_invalid_url_is_422(client):
    response = client.post(
        "/v1/tools", json={**TOOL, "slug": "bad", "url": "file:///etc/passwd"}, headers=AUTH
    )
    assert response.status_code == 422


def test_test_endpoint_renders_request(client, monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"temp": 21})

    _mock_http(monkeypatch, handler)
    assert client.post("/v1/tools", json=TOOL, headers=AUTH).status_code == 201

    result = client.post(
        "/v1/tools/weather/test",
        headers=AUTH,
        json={"params": {"city": "Minsk", "q": "a b", "days": 3}},
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["ok"] is True
    assert json.loads(body["output"]) == {"temp": 21}

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/geo/Minsk?q=a+b")
    assert captured["headers"]["x-key"] == "secret"
    assert json.loads(captured["body"]) == {"city": "Minsk", "days": 3}


def test_test_endpoint_reports_errors(client, monkeypatch):
    _mock_http(monkeypatch, lambda request: httpx.Response(500, text="boom"))
    assert client.post("/v1/tools", json=TOOL, headers=AUTH).status_code == 201
    result = client.post(
        "/v1/tools/weather/test",
        headers=AUTH,
        json={"params": {"city": "Minsk", "q": "x"}},
    ).json()
    assert result["ok"] is False
    assert result["status"] == 500
    assert result["output"].startswith("error: HTTP 500")

    missing = client.post(
        "/v1/tools/weather/test", headers=AUTH, json={"params": {"city": "Minsk"}}
    ).json()
    assert missing["ok"] is False
    assert "missing parameter" in missing["output"]


def test_agent_requires_existing_enabled_tool(client):
    agent = {
        "slug": "weather-agent",
        "name": "Weather agent",
        "system_prompt": "Use weather.",
        "tools": ["weather"],
    }
    unknown = client.post("/v1/agents", json=agent, headers=AUTH)
    assert unknown.status_code == 422
    assert "unknown tools" in unknown.json()["detail"]

    tool = client.post("/v1/tools", json=TOOL, headers=AUTH).json()
    ok = client.post("/v1/agents", json=agent, headers=AUTH)
    assert ok.status_code == 201, ok.text

    disabled = client.patch(
        f"/v1/tools/{tool['slug']}", json={"enabled": False}, headers=AUTH
    )
    assert disabled.status_code == 200
    blocked = client.patch(
        "/v1/agents/weather-agent", json={"name": "renamed"}, headers=AUTH
    )
    assert blocked.status_code == 422
    assert "disabled" in blocked.json()["detail"]


def test_tool_update_and_delete(client):
    assert client.post("/v1/tools", json=TOOL, headers=AUTH).status_code == 201
    patched = client.patch(
        "/v1/tools/weather",
        json={"description": "updated", "timeout_seconds": 9},
        headers=AUTH,
    )
    assert patched.status_code == 200
    assert patched.json()["description"] == "updated"
    assert patched.json()["timeout_seconds"] == 9

    deleted = client.delete("/v1/tools/weather", headers=AUTH)
    assert deleted.status_code == 200
    assert deleted.json() == {"slug": "weather", "detached_agents": []}
    assert client.get("/v1/tools/weather", headers=AUTH).status_code == 404


async def test_langchain_bridge_invokes_http(monkeypatch):
    from app.agents.custom_http import build_tool

    _mock_http(monkeypatch, lambda request: httpx.Response(200, text="42"))
    tool = build_tool(
        {
            "slug": "weather",
            "name": "Weather",
            "description": "forecast",
            "method": "GET",
            "url": "https://example.com/{city}",
            "headers": {},
            "query": {},
            "body_template": None,
            "content_type": "application/json",
            "parameters": [{"name": "city", "type": "string", "required": True}],
            "timeout_seconds": 5,
        }
    )
    assert tool.name == "weather"
    assert await tool.ainvoke({"city": "Minsk"}) == "42"
