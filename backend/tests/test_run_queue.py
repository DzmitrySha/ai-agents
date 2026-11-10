"""Bounded run concurrency and idempotent create."""

from __future__ import annotations

import asyncio
import time

from fastapi.testclient import TestClient

from tests.conftest import AUTH


def _wait_status(client: TestClient, run_id: str, targets: set[str], timeout: float = 8.0) -> str:
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


def test_run_gate_limits_concurrency_and_keeps_queue(db, settings, monkeypatch):
    from app.agents.events import AgentEvent
    from app.agents.plugins import PLUGINS
    from app.main import create_app
    from app.settings import Settings, get_settings

    active = 0
    active_by_prompt: dict[str, int] = {}
    peak = 0
    peak_by_prompt: dict[str, int] = {}

    async def slow(prompt, llm_config, max_steps):
        nonlocal active, peak
        active += 1
        active_by_prompt[prompt] = active_by_prompt.get(prompt, 0) + 1
        peak = max(peak, active)
        peak_by_prompt[prompt] = max(peak_by_prompt.get(prompt, 0), active_by_prompt[prompt])
        try:
            yield AgentEvent("agent.step", {"node": prompt})
            await asyncio.sleep(0.4)
            yield AgentEvent("message.delta", {"delta": "done"})
        finally:
            active -= 1
            active_by_prompt[prompt] -= 1

    PLUGINS["gate-test"] = slow
    monkeypatch.setenv("RUN_MAX_CONCURRENCY", "2")
    monkeypatch.setenv("RUN_MAX_CONCURRENCY_PER_AGENT", "1")
    get_settings.cache_clear()
    app_settings = Settings(_env_file=None)
    try:
        with TestClient(create_app(app_settings)) as client:
            for slug in ("gate-a", "gate-b"):
                response = client.post(
                    "/v1/agents",
                    json={
                        "slug": slug,
                        "name": slug,
                        "kind": "plugin",
                        "plugin_name": "gate-test",
                    },
                    headers=AUTH,
                )
                assert response.status_code == 201, response.text

            first = client.post(
                "/v1/runs", json={"agent_id": "gate-a", "input": "a"}, headers=AUTH
            ).json()["run_id"]
            second = client.post(
                "/v1/runs", json={"agent_id": "gate-b", "input": "b"}, headers=AUTH
            ).json()["run_id"]
            third = client.post(
                "/v1/runs", json={"agent_id": "gate-a", "input": "a"}, headers=AUTH
            ).json()["run_id"]

            time.sleep(0.1)
            assert client.get(f"/v1/runs/{third}", headers=AUTH).json()["status"] == "queued"
            for run_id in (first, second, third):
                _wait_status(client, run_id, {"succeeded"})
    finally:
        PLUGINS.pop("gate-test", None)

    assert peak == 2
    assert peak_by_prompt["a"] == 1
    assert peak_by_prompt["b"] == 1


def test_idempotency_key_replays_existing_run(client, fake_graph, login):
    fake_graph()
    agent = client.post(
        "/v1/agents",
        json={
            "slug": "idem-runner",
            "name": "Idem",
            "system_prompt": "hi",
        },
        headers=AUTH,
    ).json()
    client.post(
        f"/v1/agents/{agent['slug']}/publish",
        json={"visibility": "shared"},
        headers=AUTH,
    )
    headers = {**AUTH, "Idempotency-Key": "smoke-p0-1"}
    first = client.post(
        "/v1/runs", json={"agent_id": agent["slug"], "input": "hi"}, headers=headers
    )
    assert first.status_code == 201, first.text
    second = client.post(
        "/v1/runs", json={"agent_id": agent["slug"], "input": "hi"}, headers=headers
    )
    assert second.status_code == 200, second.text
    assert second.json()["run_id"] == first.json()["run_id"]
    assert client.get("/v1/runs", headers=AUTH).json()["total"] == 1

    other = login("other-idem", app_role="admin")
    third = client.post(
        "/v1/runs",
        json={"agent_id": agent["slug"], "input": "hi"},
        headers={**other, "Idempotency-Key": "smoke-p0-1"},
    )
    assert third.status_code == 201, third.text
    assert third.json()["run_id"] != first.json()["run_id"]
