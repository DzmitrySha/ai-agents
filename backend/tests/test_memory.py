"""Opt-in agent memory: tools write/search and editor API."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from tests.conftest import AUTH


def _wait(client: TestClient, run_id: str, targets: set[str], timeout: float = 8.0) -> str:
    deadline = time.time() + timeout
    status = "queued"
    while time.time() < deadline:
        response = client.get(f"/v1/runs/{run_id}", headers=AUTH)
        assert response.status_code == 200, response.text
        status = response.json()["status"]
        if status in targets:
            return status
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} stayed {status!r}")


def test_memory_write_search_and_delete(client, monkeypatch):
    from app.agents.events import AgentEvent
    from app.runtime import manager as manager_module

    created = client.post(
        "/v1/agents",
        json={
            "slug": "memory-agent",
            "name": "Memory",
            "system_prompt": "hi",
            "memory_enabled": True,
        },
        headers=AUTH,
    )
    assert created.status_code == 201, created.text
    assert created.json()["memory_enabled"] is True
    assert (
        client.post(
            "/v1/agents/memory-agent/publish",
            json={"visibility": "shared"},
            headers=AUTH,
        ).status_code
        == 200
    )

    async def fake_stream(agent, prompt, run_override, max_steps):
        assert agent.memory_hook is not None
        stored = await agent.memory_hook(
            "write",
            {
                "key": "greeting",
                "content": "alpha Bearer secret-token",
                "tags": ["note"],
            },
        )
        found = await agent.memory_hook(
            "search", {"query": "note", "limit": 5}
        )
        yield AgentEvent("message.delta", {"delta": stored + "|" + found})

    monkeypatch.setattr(manager_module, "stream_agent", fake_stream)
    run_id = client.post(
        "/v1/runs", json={"agent_id": "memory-agent", "input": "remember"}, headers=AUTH
    ).json()["run_id"]
    assert _wait(client, run_id, {"succeeded"}) == "succeeded"
    output = client.get(f"/v1/runs/{run_id}", headers=AUTH).json()["output"]
    assert "stored greeting" in output
    assert "alpha" in output
    assert "secret-token" not in output

    events = client.get(f"/v1/runs/{run_id}/events", headers=AUTH).text
    assert "memory.write" in events

    memories = client.get("/v1/agents/memory-agent/memories", headers=AUTH).json()
    assert len(memories) == 1
    assert memories[0]["key"] == "greeting"
    assert "Bearer ***" in memories[0]["content"]

    deleted = client.delete(
        f"/v1/agents/memory-agent/memories/{memories[0]['id']}", headers=AUTH
    )
    assert deleted.status_code == 204
    assert client.get("/v1/agents/memory-agent/memories", headers=AUTH).json() == []


def test_memory_requires_enabled_agent_tool(client):
    created = client.post(
        "/v1/agents",
        json={"slug": "memory-off", "name": "Off", "system_prompt": "hi"},
        headers=AUTH,
    )
    assert created.status_code == 201
    assert created.json()["memory_enabled"] is False
