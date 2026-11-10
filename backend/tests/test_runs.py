"""Runs: create/execute/SSE replay, cancel, limits, restart recovery, scopes."""

from __future__ import annotations

import time
from uuid import uuid4

from fastapi.testclient import TestClient

from tests.conftest import AUTH, insert_stale_run

PRESET = {
    "slug": "runner",
    "name": "Runner",
    "system_prompt": "Ты калькулятор.",
    "tools": ["calculator"],
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


def _wait_terminal_event(client: TestClient, run_id: str, timeout: float = 5.0) -> str:
    """Терминальное событие пишется сразу после статуса — дождёмся его, а не гоняемся."""
    deadline = time.time() + timeout
    body = ""
    while time.time() < deadline:
        with client.stream("GET", f"/v1/runs/{run_id}/events", headers=AUTH) as response:
            body = "".join(response.iter_text())
        if "event: run.completed" in body or "event: run.failed" in body:
            return body
        time.sleep(0.02)
    return body


def _published_preset(client: TestClient, **overrides) -> dict:
    payload = {**PRESET, **overrides}
    created = client.post("/v1/agents", json=payload, headers=AUTH)
    assert created.status_code == 201, created.text
    slug = created.json()["slug"]
    published = client.post(
        f"/v1/agents/{slug}/publish", json={"visibility": "shared"}, headers=AUTH
    )
    assert published.status_code == 200, published.text
    return published.json()


def test_unknown_agent_is_404(client):
    response = client.post("/v1/runs", json={"agent_id": "nope", "input": "hi"}, headers=AUTH)
    assert response.status_code == 404


def test_unpublished_agent_is_409(client):
    draft = client.post(
        "/v1/agents", json={**PRESET, "slug": "draft-only"}, headers=AUTH
    ).json()
    response = client.post(
        "/v1/runs", json={"agent_id": draft["slug"], "input": "hi"}, headers=AUTH
    )
    assert response.status_code == 409


def test_unknown_run_is_404(client):
    assert client.get("/v1/runs/nope", headers=AUTH).status_code == 404


def test_run_streams_to_completion(client, fake_graph):
    fake_graph()
    agent = _published_preset(client)
    created = client.post(
        "/v1/runs",
        json={"agent_id": agent["slug"], "input": "hi", "metadata": {"k": "v"}},
        headers=AUTH,
    )
    assert created.status_code == 201, created.text
    run = created.json()
    assert run["agent_id"] == agent["slug"]
    assert run["agent_version"] == 1
    assert len(run["harness_hash"]) == 64
    run_id = run["run_id"]

    assert _wait_status(client, run_id, {"succeeded"}) == "succeeded"
    final = client.get(f"/v1/runs/{run_id}", headers=AUTH).json()
    assert final["output"] == "hello world"
    assert final["started_at"] and final["finished_at"]

    harness = client.get(f"/v1/runs/{run_id}/harness", headers=AUTH)
    assert harness.status_code == 200, harness.text
    snapshot = harness.json()["snapshot"]
    assert harness.json()["harness_hash"] == run["harness_hash"]
    assert snapshot["agent"] == {"slug": "runner", "version": 1}
    assert snapshot["system_prompt"] == PRESET["system_prompt"]
    assert snapshot["tools"] == ["calculator"]
    assert snapshot["llm"]["model"]
    assert snapshot["limits"]["max_steps"] > 0

    digest = client.get(f"/v1/runs/{run_id}/digest", headers=AUTH)
    assert digest.status_code == 200, digest.text
    digest_body = digest.json()
    assert digest_body["agent_version"] == 1
    assert digest_body["harness_hash"] == run["harness_hash"]
    assert digest_body["status"] == "succeeded"
    assert digest_body["steps"] == 1
    assert digest_body["total_tool_calls"] == 1
    assert digest_body["failed_tool_calls"] == 0
    assert digest_body["tool_calls"] == [
        {"tool": "calculator", "calls": 1, "errors": 0}
    ]
    assert digest_body["duration_ms"] is not None
    assert digest_body["attempts"] == 1
    with client.stream("GET", f"/v1/runs/{run_id}/events", headers=AUTH) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())

    positions = [
        body.index(f"event: {name}")
        for name in ("run.started", "message.delta", "tool.call", "tool.result", "agent.step", "run.completed")
    ]
    assert positions == sorted(positions)
    assert "hello" in body and "world" in body

    listed = client.get("/v1/runs", headers=AUTH).json()
    assert listed["total"] == 1
    assert listed["items"][0]["run_id"] == run_id


def test_events_replay_after_restart(db, settings, fake_graph):
    fake_graph()
    from app.main import create_app

    with TestClient(create_app(settings)) as first:
        agent = _published_preset(first)
        run_id = first.post(
            "/v1/runs", json={"agent_id": agent["slug"], "input": "hi"}, headers=AUTH
        ).json()["run_id"]
        _wait_status(first, run_id, {"succeeded"})

    with TestClient(create_app(settings)) as restarted:
        body = _wait_terminal_event(restarted, run_id)
        assert "event: run.started" in body
        assert "event: run.completed" in body
        assert restarted.get(f"/v1/runs/{run_id}", headers=AUTH).json()["status"] == "succeeded"


def test_cancel_running_run(client):
    from app.agents.events import AgentEvent
    from app.agents.plugins import PLUGINS

    async def slow(prompt, llm_config, max_steps):
        yield AgentEvent("message.delta", {"delta": "working"})
        yield AgentEvent(
            "token.usage",
            {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        )
        import asyncio

        await asyncio.sleep(30)
        yield AgentEvent("message.delta", {"delta": "never"})

    PLUGINS["slow-test"] = slow
    try:
        created = client.post(
            "/v1/agents",
            json={"slug": "slow-run", "name": "slow", "kind": "plugin", "plugin_name": "slow-test"},
            headers=AUTH,
        )
        assert created.status_code == 201, created.text
        run_id = client.post(
            "/v1/runs", json={"agent_id": "slow-run", "input": "wait"}, headers=AUTH
        ).json()["run_id"]
        _wait_status(client, run_id, {"running"})

        cancelled = client.post(f"/v1/runs/{run_id}/cancel", headers=AUTH)
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert _wait_status(client, run_id, {"cancelled"}) == "cancelled"
        deadline = time.time() + 5
        while time.time() < deadline:
            run = client.get(f"/v1/runs/{run_id}", headers=AUTH).json()
            if run["total_tokens"] == 10:
                break
            time.sleep(0.02)
        assert run["total_tokens"] == 10

        with client.stream("GET", f"/v1/runs/{run_id}/events", headers=AUTH) as response:
            body = "".join(response.iter_text())
        assert "event: run.cancelled" in body
    finally:
        PLUGINS.pop("slow-test", None)


def test_max_steps_limit_fails_run(client, fake_graph):
    from app.agents.events import AgentEvent
    from app.agents.plugins import PLUGINS

    async def endless(prompt, llm_config, max_steps):
        for index in range(5):
            yield AgentEvent("agent.step", {"step": index})

    PLUGINS["endless-test"] = endless
    try:
        client.post(
            "/v1/agents",
            json={
                "slug": "endless",
                "name": "endless",
                "kind": "plugin",
                "plugin_name": "endless-test",
                "limits": {"max_steps": 1, "timeout_seconds": 30},
            },
            headers=AUTH,
        )
        run_id = client.post(
            "/v1/runs", json={"agent_id": "endless", "input": "go"}, headers=AUTH
        ).json()["run_id"]
        assert _wait_status(client, run_id, {"failed"}) == "failed"
        run = client.get(f"/v1/runs/{run_id}", headers=AUTH).json()
        assert "max_steps" in run["error"]
        assert run["failure_kind"] == "step_limit"
        assert run["attempts"] == 1
    finally:
        PLUGINS.pop("endless-test", None)


def test_run_records_token_usage(client, fake_graph):
    fake_graph(usage={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10})
    agent = _published_preset(client)
    created = client.post(
        "/v1/runs", json={"agent_id": agent["slug"], "input": "hi"}, headers=AUTH
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["run_id"]
    assert _wait_status(client, run_id, {"succeeded"}) == "succeeded"

    run = client.get(f"/v1/runs/{run_id}", headers=AUTH).json()
    assert run["prompt_tokens"] == 7
    assert run["completion_tokens"] == 3
    assert run["total_tokens"] == 10

    digest = client.get(f"/v1/runs/{run_id}/digest", headers=AUTH).json()
    assert digest["prompt_tokens"] == 7
    assert digest["completion_tokens"] == 3
    assert digest["total_tokens"] == 10

    with client.stream("GET", f"/v1/runs/{run_id}/events", headers=AUTH) as response:
        body = "".join(response.iter_text())
    assert "event: token.usage" in body
    assert '"total_tokens": 10' in body

    stats = client.get("/v1/stats/overview?days=7", headers=AUTH).json()
    assert stats["tokens_total"] >= 10
    assert any(item["tokens"] >= 10 for item in stats["top_agents"])


def test_agent_token_budget_fails_run(client, fake_graph):
    fake_graph(usage={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10})
    agent = _published_preset(
        client,
        limits={"max_tokens": 1, "max_steps": 8, "timeout_seconds": 30},
    )
    run_id = client.post(
        "/v1/runs", json={"agent_id": agent["slug"], "input": "hi"}, headers=AUTH
    ).json()["run_id"]
    assert _wait_status(client, run_id, {"failed"}) == "failed"
    run = client.get(f"/v1/runs/{run_id}", headers=AUTH).json()
    assert "token budget exceeded (10 > 1)" in run["error"]
    assert run["failure_kind"] == "token_budget"
    assert run["attempts"] == 1
    assert run["total_tokens"] == 10
    digest = client.get(f"/v1/runs/{run_id}/digest", headers=AUTH).json()
    assert digest["total_tokens"] == 10


def test_daily_token_budget(client, fake_graph, login, monkeypatch):
    headers = login("budget-user", app_role="user")
    monkeypatch.setenv("USER_DAILY_TOKEN_LIMIT", "5")
    from app.settings import get_settings

    get_settings.cache_clear()
    fake_graph(usage={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10})
    agent = _published_preset(client)
    first = client.post(
        "/v1/runs", json={"agent_id": agent["slug"], "input": "hi"}, headers=headers
    )
    assert first.status_code == 201, first.text
    _wait_status(client, first.json()["run_id"], {"succeeded"})

    second = client.post(
        "/v1/runs", json={"agent_id": agent["slug"], "input": "hi"}, headers=headers
    )
    assert second.status_code == 429, second.text
    assert "daily token budget" in second.json()["detail"]


def test_agent_failure_marks_run_failed(client, fake_graph):
    fake_graph(failure=RuntimeError("boom"))
    agent = _published_preset(client)
    run_id = client.post(
        "/v1/runs", json={"agent_id": agent["slug"], "input": "hi"}, headers=AUTH
    ).json()["run_id"]
    assert _wait_status(client, run_id, {"failed"}) == "failed"
    run = client.get(f"/v1/runs/{run_id}", headers=AUTH).json()
    assert "RuntimeError: boom" in run["error"]

    digest = client.get(f"/v1/runs/{run_id}/digest", headers=AUTH).json()
    assert digest["status"] == "failed"
    assert "boom" in digest["error"]


def test_recover_stale_runs_on_startup(db, settings):
    run_id = str(uuid4())
    insert_stale_run(run_id)

    from app.main import create_app

    with TestClient(create_app(settings)) as restarted:
        body = restarted.get(f"/v1/runs/{run_id}", headers=AUTH).json()
        assert body["status"] == "failed"
        assert body["error"] == "server restarted"
        with restarted.stream("GET", f"/v1/runs/{run_id}/events", headers=AUTH) as response:
            sse = "".join(response.iter_text())
        assert "event: run.failed" in sse
        assert "server restarted" in sse


def test_service_key_without_runs_write_is_403(client, login):
    admin_headers = login("root", is_superadmin=True)
    key = client.post(
        "/api/admin/service-keys",
        headers=admin_headers,
        json={"name": "agent-reader", "scopes": ["agents:read"]},
    ).json()["key"]
    bearer = {"Authorization": f"Bearer {key}"}
    agent = _published_preset(client)
    response = client.post(
        "/v1/runs", json={"agent_id": agent["slug"], "input": "hi"}, headers=bearer
    )
    assert response.status_code == 403
