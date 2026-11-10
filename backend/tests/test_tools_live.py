"""Live custom tools: edits apply without republishing; deletion detaches agents."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from tests.conftest import AUTH

TOOL = {
    "slug": "weather",
    "name": "Weather",
    "description": "Forecast",
    "method": "GET",
    "url": "https://api.test/forecast?hourly=temperature_2m",
    "parameters": [],
}

AGENT = {
    "slug": "weather-agent",
    "name": "Weather agent",
    "system_prompt": "Ты погодный агент.",
    "tools": ["weather"],
}


def _wait_status(client: TestClient, run_id: str, targets: set[str], timeout: float = 5.0) -> str:
    deadline = time.time() + timeout
    status = "queued"
    while time.time() < deadline:
        response = client.get(f"/v1/runs/{run_id}", headers=AUTH)
        assert response.status_code == 200, response.text
        status = response.json()["status"]
        if status in targets:
            return status
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} stayed {status!r}, expected one of {targets}")


def _publish_agent(client: TestClient) -> None:
    created = client.post("/v1/agents", json=AGENT, headers=AUTH)
    assert created.status_code == 201, created.text
    published = client.post(
        "/v1/agents/weather-agent/publish", json={"visibility": "shared"}, headers=AUTH
    )
    assert published.status_code == 200, published.text


def _capture_configs(monkeypatch) -> list:
    """Replace the agent graph so runs finish immediately and expose AgentConfig."""
    from app.agents.events import AgentEvent
    from app.runtime import manager as manager_module

    seen: list = []

    async def fake_stream(config, prompt, run_override, max_steps):
        seen.append(config)
        yield AgentEvent("message.delta", {"delta": "ok"})
        yield AgentEvent("agent.step", {"node": "fake"})

    monkeypatch.setattr(manager_module, "stream_agent", fake_stream)
    return seen


def _run(client: TestClient) -> None:
    created = client.post(
        "/v1/runs", json={"agent_id": "weather-agent", "input": "погода"}, headers=AUTH
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["run_id"]
    assert _wait_status(client, run_id, {"succeeded", "failed"}) == "succeeded"


def test_tool_edit_applies_without_republish(client, monkeypatch):
    assert client.post("/v1/tools", json=TOOL, headers=AUTH).status_code == 201
    _publish_agent(client)
    configs = _capture_configs(monkeypatch)

    _run(client)
    assert configs[0].tool_defs[0]["url"] == TOOL["url"]

    updated = client.patch(
        "/v1/tools/weather",
        json={"url": "https://api.test/forecast?hourly=temperature_2m,precipitation"},
        headers=AUTH,
    )
    assert updated.status_code == 200, updated.text

    _run(client)
    # Без перепубликации агент берёт актуальное определение инструмента.
    assert configs[1].tool_defs[0]["url"].endswith("temperature_2m,precipitation")


def test_tool_usage_lists_agents(client):
    assert client.post("/v1/tools", json=TOOL, headers=AUTH).status_code == 201
    _publish_agent(client)

    usage = client.get("/v1/tools/weather/usage", headers=AUTH)

    assert usage.status_code == 200
    body = usage.json()
    assert body["slug"] == "weather"
    assert body["total"] == 1
    assert body["agents"][0]["slug"] == "weather-agent"
    assert body["agents"][0]["published_version"] == 1


def test_delete_tool_detaches_agents(client, monkeypatch):
    assert client.post("/v1/tools", json=TOOL, headers=AUTH).status_code == 201
    _publish_agent(client)
    _capture_configs(monkeypatch)

    deleted = client.delete("/v1/tools/weather", headers=AUTH)

    assert deleted.status_code == 200
    assert deleted.json() == {"slug": "weather", "detached_agents": ["weather-agent"]}

    agent = client.get("/v1/agents/weather-agent", headers=AUTH).json()
    assert agent["tools"] == []
    assert client.get("/v1/tools/weather/usage", headers=AUTH).status_code == 404

    # Агент без инструментов запускается нормально.
    _run(client)
