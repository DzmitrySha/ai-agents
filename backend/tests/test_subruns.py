"""Typed sub-agent runs: parent/child linkage, limits and API."""

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


def _agent(client: TestClient, slug: str, **extra) -> dict:
    created = client.post(
        "/v1/agents",
        json={"slug": slug, "name": slug, "system_prompt": "hi", **extra},
        headers=AUTH,
    )
    assert created.status_code == 201, created.text
    published = client.post(
        f"/v1/agents/{slug}/publish", json={"visibility": "shared"}, headers=AUTH
    )
    assert published.status_code == 200, published.text
    return published.json()


def _patch_stream(monkeypatch, calls: int = 1) -> None:
    from app.agents.events import AgentEvent
    from app.runtime import manager as manager_module

    async def fake_stream(agent, prompt, run_override, max_steps):
        if prompt == "parent":
            results = []
            for index in range(calls):
                if agent.subrun_hook is not None:
                    results.append(
                        await agent.subrun_hook("child-agent", f"child {index}")
                    )
            yield AgentEvent("message.delta", {"delta": "|".join(results)})
        else:
            yield AgentEvent("message.delta", {"delta": "child result"})

    monkeypatch.setattr(manager_module, "stream_agent", fake_stream)


def test_parent_calls_child_and_links_runs(client, monkeypatch):
    _agent(client, "child-agent")
    parent = _agent(client, "parent-agent", sub_agents=["child-agent"])
    assert parent["sub_agents"] == ["child-agent"]
    _patch_stream(monkeypatch)

    created = client.post(
        "/v1/runs", json={"agent_id": "parent-agent", "input": "parent"}, headers=AUTH
    )
    assert created.status_code == 201, created.text
    parent_id = created.json()["run_id"]
    assert _wait(client, parent_id, {"succeeded"}) == "succeeded"

    run = client.get(f"/v1/runs/{parent_id}", headers=AUTH).json()
    assert run["output"] == "child result"
    assert run["parent_run_id"] is None
    assert run["depth"] == 0

    children = client.get(
        f"/v1/runs?parent_run_id={parent_id}", headers=AUTH
    ).json()["items"]
    assert len(children) == 1
    child = children[0]
    assert child["agent_id"] == "child-agent"
    assert child["parent_run_id"] == parent_id
    assert child["depth"] == 1


def test_subrun_count_limit(client, settings, monkeypatch):
    settings.run_max_subruns_per_run = 1
    _agent(client, "child-agent")
    _agent(client, "parent-limit", sub_agents=["child-agent"])
    _patch_stream(monkeypatch, calls=2)

    run_id = client.post(
        "/v1/runs",
        json={"agent_id": "parent-limit", "input": "parent"},
        headers=AUTH,
    ).json()["run_id"]
    assert _wait(client, run_id, {"succeeded"}) == "succeeded"
    output = client.get(f"/v1/runs/{run_id}", headers=AUTH).json()["output"]
    assert "subrun count limit exceeded" in output
    children = client.get(
        f"/v1/runs?parent_run_id={run_id}", headers=AUTH
    ).json()["items"]
    assert len(children) == 1


def test_subrun_tool_rejects_unknown_agent():
    import asyncio

    from app.agents.execution import _build_subrun_tool

    async def hook(agent_slug, prompt):
        return f"called {agent_slug}"

    async def main() -> str:
        tool = _build_subrun_tool(["allowed"], hook)
        return await tool.ainvoke({"agent_slug": "other", "input": "hi"})

    assert "not allowed" in asyncio.run(main())
