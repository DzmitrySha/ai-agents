"""Live skills/tools at run + skills_stale/tools_stale after publish."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from tests.conftest import AUTH

SKILL = {
    "name": "Tone",
    "slug": "tone",
    "content": "---\nname: tone\n---\nSpeak softly.\n",
}

TOOL = {
    "slug": "echo-http",
    "name": "Echo HTTP",
    "description": "Probe",
    "method": "GET",
    "url": "https://api.test/v1",
    "parameters": [],
}

AGENT = {
    "slug": "stale-agent",
    "name": "Stale agent",
    "system_prompt": "Base",
    "skills": ["tone"],
    "tools": ["echo-http"],
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


def _capture_configs(monkeypatch) -> list:
    from app.agents.events import AgentEvent
    from app.runtime import manager as manager_module

    seen: list = []

    async def fake_stream(config, prompt, run_override, max_steps):
        seen.append(config)
        yield AgentEvent("message.delta", {"delta": "ok"})
        yield AgentEvent("agent.step", {"node": "fake"})

    monkeypatch.setattr(manager_module, "stream_agent", fake_stream)
    return seen


def _seed_and_publish(client: TestClient) -> dict:
    assert client.post("/v1/skills", json=SKILL, headers=AUTH).status_code == 201
    assert client.post("/v1/tools", json=TOOL, headers=AUTH).status_code == 201
    created = client.post("/v1/agents", json=AGENT, headers=AUTH)
    assert created.status_code == 201, created.text
    published = client.post(
        "/v1/agents/stale-agent/publish", json={"visibility": "shared"}, headers=AUTH
    )
    assert published.status_code == 200, published.text
    body = published.json()
    assert body["skills_stale"] is False
    assert body["tools_stale"] is False
    assert body["published_version"] == 1
    return body


def _run(client: TestClient) -> None:
    created = client.post(
        "/v1/runs", json={"agent_id": "stale-agent", "input": "hi"}, headers=AUTH
    )
    assert created.status_code == 201, created.text
    assert _wait_status(client, created.json()["run_id"], {"succeeded", "failed"}) == "succeeded"


def test_skill_edit_is_live_and_marks_skills_stale(client, monkeypatch):
    _seed_and_publish(client)
    configs = _capture_configs(monkeypatch)

    _run(client)
    assert "Speak softly" in configs[0].skill_defs[0]["content"]

    patched = client.patch(
        "/v1/skills/tone",
        json={"content": "---\nname: tone\n---\nSpeak boldly.\n"},
        headers=AUTH,
    )
    assert patched.status_code == 200, patched.text

    agent = client.get("/v1/agents/stale-agent", headers=AUTH).json()
    assert agent["skills_stale"] is True
    assert agent["tools_stale"] is False

    _run(client)
    assert "Speak boldly" in configs[1].skill_defs[0]["content"]

    listed = client.get("/v1/agents?scope=owned&stale=skills", headers=AUTH).json()
    assert any(item["slug"] == "stale-agent" for item in listed["items"])


def test_tool_edit_marks_tools_stale_and_run_is_live(client, monkeypatch):
    _seed_and_publish(client)
    configs = _capture_configs(monkeypatch)

    patched = client.patch(
        "/v1/tools/echo-http",
        json={"url": "https://api.test/v2"},
        headers=AUTH,
    )
    assert patched.status_code == 200, patched.text

    agent = client.get("/v1/agents/stale-agent", headers=AUTH).json()
    assert agent["tools_stale"] is True
    assert agent["skills_stale"] is False

    _run(client)
    assert configs[0].tool_defs[0]["url"] == "https://api.test/v2"

    listed = client.get("/v1/agents?scope=owned&stale=tools", headers=AUTH).json()
    assert any(item["slug"] == "stale-agent" for item in listed["items"])


def test_republish_clears_stale_flags(client, monkeypatch):
    _seed_and_publish(client)
    _capture_configs(monkeypatch)

    assert (
        client.patch(
            "/v1/skills/tone",
            json={"content": "---\nname: tone\n---\nUpdated.\n"},
            headers=AUTH,
        ).status_code
        == 200
    )
    assert (
        client.patch(
            "/v1/tools/echo-http",
            json={"url": "https://api.test/v3"},
            headers=AUTH,
        ).status_code
        == 200
    )

    before = client.get("/v1/agents/stale-agent", headers=AUTH).json()
    assert before["skills_stale"] is True
    assert before["tools_stale"] is True

    any_stale = client.get("/v1/agents?scope=owned&stale=any", headers=AUTH).json()
    assert any(item["slug"] == "stale-agent" for item in any_stale["items"])

    again = client.post(
        "/v1/agents/stale-agent/publish", json={"visibility": "shared"}, headers=AUTH
    )
    assert again.status_code == 200, again.text
    body = again.json()
    assert body["published_version"] == 2
    assert body["skills_stale"] is False
    assert body["tools_stale"] is False

    cleared = client.get("/v1/agents?scope=owned&stale=any", headers=AUTH).json()
    assert all(item["slug"] != "stale-agent" for item in cleared["items"])


def test_draft_has_no_stale_flags(client):
    assert client.post("/v1/skills", json=SKILL, headers=AUTH).status_code == 201
    created = client.post(
        "/v1/agents",
        json={
            "slug": "draft-only",
            "name": "Draft",
            "system_prompt": "x",
            "skills": ["tone"],
        },
        headers=AUTH,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["published_version"] is None
    assert body["skills_stale"] is False
    assert body["tools_stale"] is False
