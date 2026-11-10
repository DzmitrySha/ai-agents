"""Preflight: read-only readiness checks before a run is created."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import AUTH

AGENT = {
    "slug": "preflight-agent",
    "name": "Preflight",
    "system_prompt": "You are a demo.",
    "tools": ["calculator"],
    "limits": {"max_steps": 3, "timeout_seconds": 30},
}

CHECKS = ["agent", "plugin", "quota", "tools", "skills", "mcp", "llm", "limits"]


def _publish(client: TestClient, payload: dict | None = None) -> dict:
    body = payload or AGENT
    created = client.post("/v1/agents", json=body, headers=AUTH)
    assert created.status_code == 201, created.text
    published = client.post(
        f"/v1/agents/{body['slug']}/publish", json={"visibility": "shared"}, headers=AUTH
    )
    assert published.status_code == 200, published.text
    return published.json()


def _check(body: dict, check_id: str) -> dict:
    return next(item for item in body["checks"] if item["id"] == check_id)


def test_preflight_ok(client, monkeypatch):
    from app.runtime import preflight

    async def _models(*args, **kwargs):
        return ["test-model"]

    monkeypatch.setattr(preflight, "fetch_models", _models)
    agent = _publish(client)

    response = client.post(
        "/v1/runs/preflight", json={"agent_id": agent["slug"]}, headers=AUTH
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert [item["id"] for item in body["checks"]] == CHECKS
    assert _check(body, "agent")["status"] == "ok"
    assert _check(body, "plugin")["status"] == "skip"
    assert _check(body, "quota")["status"] == "ok"
    assert _check(body, "llm")["status"] == "ok"
    assert body["effective"]["agent_version"] == 1
    assert body["effective"]["max_steps"] == 3
    assert body["effective"]["tools"] == ["calculator"]
    assert isinstance(body["effective"]["timeout_seconds"], float)
    assert body["effective"]["max_tokens"] > 0
    assert body["effective"]["max_attempts"] >= 1
    assert body["effective"]["approval_mode"] in {"never", "mutating", "all"}
    assert body["effective"]["sub_agents"] == []
    assert "max_tokens=" in _check(body, "limits")["message"]
    assert "max_attempts=" in _check(body, "limits")["message"]


def test_preflight_model_not_listed_is_warning(client, monkeypatch):
    from app.runtime import preflight

    async def _models(*args, **kwargs):
        return ["other-model"]

    monkeypatch.setattr(preflight, "fetch_models", _models)
    agent = _publish(client, {**AGENT, "slug": "preflight-warn"})

    body = client.post(
        "/v1/runs/preflight", json={"agent_id": agent["slug"]}, headers=AUTH
    ).json()
    assert body["ok"] is True
    assert _check(body, "llm")["status"] == "warn"


def test_preflight_llm_failure_is_error(client, monkeypatch):
    from app.runtime import preflight
    from app.runtime.llm_config import ModelsError

    async def _models(*args, **kwargs):
        raise ModelsError("boom")

    monkeypatch.setattr(preflight, "fetch_models", _models)
    agent = _publish(client, {**AGENT, "slug": "preflight-llm-down"})

    body = client.post(
        "/v1/runs/preflight", json={"agent_id": agent["slug"]}, headers=AUTH
    ).json()
    assert body["ok"] is False
    assert _check(body, "llm")["status"] == "error"
    assert "boom" in _check(body, "llm")["message"]


def test_preflight_missing_mcp_tool_is_error(client, monkeypatch):
    from app.runtime import preflight

    async def _models(*args, **kwargs):
        return ["test-model"]

    async def _no_tools(*args, **kwargs):
        return []

    monkeypatch.setattr(preflight, "fetch_models", _models)
    monkeypatch.setattr(preflight, "list_remote_tools", _no_tools)
    connection = {
        "slug": "docs",
        "name": "Docs",
        "url": "https://mcp.test/mcp",
        "headers": {"Authorization": "Bearer secret"},
        "timeout_seconds": 15,
        "enabled": True,
    }
    assert client.post("/v1/mcp-connections", json=connection, headers=AUTH).status_code == 201
    agent = _publish(
        client,
        {
            "slug": "preflight-mcp",
            "name": "Preflight MCP",
            "system_prompt": "demo",
            "tools": ["mcp:docs:missing"],
        },
    )

    body = client.post(
        "/v1/runs/preflight", json={"agent_id": agent["slug"]}, headers=AUTH
    ).json()
    assert body["ok"] is False
    mcp = _check(body, "mcp")
    assert mcp["status"] == "error"
    assert "mcp:docs:missing" in mcp["message"]


def test_preflight_unpublished_is_409(client):
    created = client.post(
        "/v1/agents", json={**AGENT, "slug": "preflight-draft"}, headers=AUTH
    )
    assert created.status_code == 201, created.text
    response = client.post(
        "/v1/runs/preflight", json={"agent_id": "preflight-draft"}, headers=AUTH
    )
    assert response.status_code == 409


def test_preflight_unknown_is_404(client):
    response = client.post(
        "/v1/runs/preflight", json={"agent_id": "nope"}, headers=AUTH
    )
    assert response.status_code == 404
