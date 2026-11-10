"""Human approval gates for mutating tools."""

from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import AUTH

AGENT = {
    "slug": "approval-agent",
    "name": "Approval",
    "system_prompt": "hi",
    "limits": {"max_steps": 8, "timeout_seconds": 30, "approval_mode": "mutating"},
}


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


def _published(client: TestClient, slug: str = "approval-agent") -> dict:
    created = client.post("/v1/agents", json={**AGENT, "slug": slug}, headers=AUTH)
    assert created.status_code == 201, created.text
    published = client.post(
        f"/v1/agents/{slug}/publish", json={"visibility": "shared"}, headers=AUTH
    )
    assert published.status_code == 200, published.text
    return published.json()


def _patch_stream(monkeypatch) -> None:
    from app.agents.approval import APPROVAL_REJECTED_PREFIX, ApprovalDenied
    from app.agents.events import AgentEvent
    from app.runtime import manager as manager_module

    async def fake_stream(agent, prompt, run_override, max_steps):
        if agent.approval_hook is not None:
            try:
                await agent.approval_hook(
                    "danger_tool", {"token": "Bearer secret-token"}
                )
            except ApprovalDenied as exc:
                yield AgentEvent("tool.call", {"tool": "danger_tool", "input": {}})
                yield AgentEvent(
                    "tool.result",
                    {
                        "tool": "danger_tool",
                        "output": f"{APPROVAL_REJECTED_PREFIX} {exc}",
                    },
                )
                return
        yield AgentEvent("tool.call", {"tool": "danger_tool", "input": {}})
        yield AgentEvent("tool.result", {"tool": "danger_tool", "output": "ok"})
        yield AgentEvent("message.delta", {"delta": "done"})

    monkeypatch.setattr(manager_module, "stream_agent", fake_stream)


def test_approval_tool_allows_and_denies():
    import asyncio

    from app.agents.approval import ApprovalDenied, ApprovalTool
    from app.agents.tools import calculator

    async def approve(name: str, kwargs: dict[str, Any]) -> None:
        assert name == "calculator"
        assert kwargs == {"expression": "1+1"}

    async def deny(name: str, kwargs: dict[str, Any]) -> None:
        raise ApprovalDenied("no")

    async def main() -> tuple[str, str]:
        allowed = await ApprovalTool.wrap(calculator, approve).ainvoke(
            {"expression": "1+1"}
        )
        rejected = await ApprovalTool.wrap(calculator, deny).ainvoke(
            {"expression": "1+1"}
        )
        return allowed, rejected

    allowed, rejected = asyncio.run(main())
    assert allowed == "2"
    assert rejected.startswith("error: approval rejected:")


def test_approval_tool_selection_by_method():
    from app.agents.approval import ApprovalTool
    from app.agents.execution import _agent_tools

    async def hook(name: str, kwargs: dict[str, Any]) -> None:
        return None

    definition = {
        "slug": "mutate",
        "method": "POST",
        "url": "https://example.com",
        "parameters": [],
    }
    wrapped = _agent_tools(
        ["mutate"], [definition], approval_hook=hook, approval_mode="mutating"
    )
    assert isinstance(wrapped[0], ApprovalTool)
    read_only = _agent_tools(
        ["calculator"], [], approval_hook=hook, approval_mode="mutating"
    )
    assert not isinstance(read_only[0], ApprovalTool)


def test_approve_mutating_tool(client, monkeypatch):
    _patch_stream(monkeypatch)
    agent = _published(client)
    run_id = client.post(
        "/v1/runs", json={"agent_id": agent["slug"], "input": "hi"}, headers=AUTH
    ).json()["run_id"]
    assert _wait_status(client, run_id, {"waiting_approval"}) == "waiting_approval"

    approvals = client.get(
        f"/v1/runs/{run_id}/approvals", headers=AUTH
    ).json()
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval["status"] == "pending"
    assert approval["tool"] == "danger_tool"
    assert "secret-token" not in str(approval["input"])

    decided = client.post(
        f"/v1/runs/{run_id}/approvals/{approval['id']}",
        json={"decision": "approve"},
        headers=AUTH,
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "approved"
    assert _wait_status(client, run_id, {"succeeded"}) == "succeeded"


def test_reject_mutating_tool_fails_run(client, monkeypatch):
    _patch_stream(monkeypatch)
    agent = _published(client, "approval-reject")
    run_id = client.post(
        "/v1/runs", json={"agent_id": agent["slug"], "input": "hi"}, headers=AUTH
    ).json()["run_id"]
    _wait_status(client, run_id, {"waiting_approval"})
    approval = client.get(f"/v1/runs/{run_id}/approvals", headers=AUTH).json()[0]

    decided = client.post(
        f"/v1/runs/{run_id}/approvals/{approval['id']}",
        json={"decision": "reject"},
        headers=AUTH,
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "rejected"
    assert _wait_status(client, run_id, {"failed"}) == "failed"
    run = client.get(f"/v1/runs/{run_id}", headers=AUTH).json()
    assert run["failure_kind"] == "approval_rejected"
    assert "rejected" in run["error"]


def test_cancel_waiting_approval_expires(client, monkeypatch):
    _patch_stream(monkeypatch)
    agent = _published(client, "approval-cancel")
    run_id = client.post(
        "/v1/runs", json={"agent_id": agent["slug"], "input": "hi"}, headers=AUTH
    ).json()["run_id"]
    _wait_status(client, run_id, {"waiting_approval"})
    cancelled = client.post(f"/v1/runs/{run_id}/cancel", headers=AUTH)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    approvals = client.get(f"/v1/runs/{run_id}/approvals", headers=AUTH).json()
    assert approvals[0]["status"] == "expired"


def test_approval_timeout_expires(client, monkeypatch):
    _patch_stream(monkeypatch)
    client.app.state.settings.run_approval_timeout_seconds = 0.05
    client.app.state.run_manager._settings.run_approval_timeout_seconds = 0.05
    agent = _published(client, "approval-timeout")
    run_id = client.post(
        "/v1/runs", json={"agent_id": agent["slug"], "input": "hi"}, headers=AUTH
    ).json()["run_id"]
    assert _wait_status(client, run_id, {"failed"}) == "failed"
    approvals = client.get(f"/v1/runs/{run_id}/approvals", headers=AUTH).json()
    assert approvals[0]["status"] == "expired"
    run = client.get(f"/v1/runs/{run_id}", headers=AUTH).json()
    assert run["failure_kind"] == "approval_rejected"
    assert "timed out" in run["error"]
