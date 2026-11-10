"""Compare two runs: harness diff, digests, visibility, validation."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from tests.conftest import AUTH

PRESET = {
    "slug": "compare-agent",
    "name": "Compare",
    "system_prompt": "You are a demo.",
    "tools": ["calculator"],
}

DIFF_FIELDS = [
    "agent_version",
    "harness_hash",
    "model",
    "base_url",
    "max_steps",
    "timeout_seconds",
    "max_tokens",
    "max_attempts",
    "fallback_model",
    "approval_mode",
    "context_max_tokens",
    "skills_mode",
    "tools",
    "skills",
    "sub_agents",
    "mcp",
    "prompt_chars",
    "status",
    "steps",
    "total_tool_calls",
    "failed_tool_calls",
]


def _published(client: TestClient, headers: dict | None = None) -> dict:
    h = headers or AUTH
    created = client.post("/v1/agents", json=PRESET, headers=h)
    assert created.status_code == 201, created.text
    published = client.post(
        "/v1/agents/compare-agent/publish", json={"visibility": "shared"}, headers=h
    )
    assert published.status_code == 200, published.text
    return published.json()


def _run(client: TestClient, headers: dict | None = None, agent: str = "compare-agent") -> str:
    response = client.post(
        "/v1/runs",
        json={"agent_id": agent, "input": "hi"},
        headers=headers or AUTH,
    )
    assert response.status_code == 201, response.text
    run_id = response.json()["run_id"]
    deadline = time.time() + 5
    while time.time() < deadline:
        status = client.get(f"/v1/runs/{run_id}", headers=headers or AUTH).json()["status"]
        if status in {"succeeded", "failed", "cancelled"}:
            return run_id
        time.sleep(0.02)
    raise AssertionError("run did not finish")


def test_compare_two_runs(client, fake_graph):
    fake_graph()
    _published(client)
    left = _run(client)
    right = _run(client)

    response = client.get(
        f"/v1/runs/compare?left={left}&right={right}", headers=AUTH
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["left"]["run_id"] == left
    assert body["right"]["run_id"] == right
    assert body["left_digest"]["steps"] == 1
    assert body["right_digest"]["total_tool_calls"] == 1
    assert [item["field"] for item in body["diff"]] == DIFF_FIELDS
    by_field = {item["field"]: item for item in body["diff"]}
    assert by_field["agent_version"]["changed"] is False
    assert by_field["harness_hash"]["changed"] is False
    assert by_field["steps"]["changed"] is False
    assert body["left"]["harness_hash"] == body["right"]["harness_hash"]


def test_compare_same_run_is_422(client, fake_graph):
    fake_graph()
    _published(client)
    run_id = _run(client)
    response = client.get(
        f"/v1/runs/compare?left={run_id}&right={run_id}", headers=AUTH
    )
    assert response.status_code == 422


def test_compare_unknown_is_404(client):
    response = client.get(
        "/v1/runs/compare?left=nope&right=other", headers=AUTH
    )
    assert response.status_code == 404


def test_compare_foreign_runs_is_404(client, login, fake_graph):
    fake_graph()
    user = login("owner")
    created = client.post(
        "/v1/agents", json={**PRESET, "slug": "owner-agent"}, headers=user
    )
    assert created.status_code == 201, created.text
    published = client.post(
        "/v1/agents/owner-agent/publish", json={"visibility": "shared"}, headers=user
    )
    assert published.status_code == 200, published.text
    left = _run(client, user, "owner-agent")
    right = _run(client, user, "owner-agent")

    other = login("stranger")
    response = client.get(
        f"/v1/runs/compare?left={left}&right={right}", headers=other
    )
    assert response.status_code == 404
