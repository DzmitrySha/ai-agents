"""Failure taxonomy and bounded retry/fallback."""

from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import AUTH

PRESET = {
    "slug": "retry-agent",
    "name": "Retry",
    "system_prompt": "hi",
}


class TransientError(RuntimeError):
    status_code = 503


class RateLimitError(RuntimeError):
    status_code = 429


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


def _published(client: TestClient, *, slug: str = "retry-agent", **overrides: Any) -> dict:
    payload = {**PRESET, "slug": slug, **overrides}
    created = client.post("/v1/agents", json=payload, headers=AUTH)
    assert created.status_code == 201, created.text
    published = client.post(
        f"/v1/agents/{slug}/publish", json={"visibility": "shared"}, headers=AUTH
    )
    assert published.status_code == 200, published.text
    return published.json()


def test_classify_failure_and_retryability():
    from app.runtime.failures import (
        classify_failure,
        failure_is_retryable,
    )

    assert classify_failure(TransientError("down")) == "transient"
    assert classify_failure(RateLimitError("slow")) == "rate_limit"
    assert classify_failure(TimeoutError()) == "timeout"
    assert classify_failure(RuntimeError("boom")) == "internal"
    assert classify_failure(RuntimeError("boom"), tool_calls=1) == "tool"
    assert classify_failure(None, token_budget=True) == "token_budget"
    assert classify_failure(None, step_limit=True) == "step_limit"
    assert failure_is_retryable("transient", tool_calls=0)
    assert not failure_is_retryable("transient", tool_calls=1)
    assert not failure_is_retryable("timeout", tool_calls=0)


def test_transient_failure_retries_and_sums_usage(client, settings, fake_graph):
    settings.run_retry_backoff_seconds = 0
    fake_graph(
        failures=[TransientError("temporary")],
        usage={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
    )
    agent = _published(client)
    run_id = client.post(
        "/v1/runs", json={"agent_id": agent["slug"], "input": "hi"}, headers=AUTH
    ).json()["run_id"]
    assert _wait_status(client, run_id, {"succeeded"}) == "succeeded"

    run = client.get(f"/v1/runs/{run_id}", headers=AUTH).json()
    assert run["attempts"] == 2
    assert run["failure_kind"] is None
    assert run["total_tokens"] == 10
    with client.stream("GET", f"/v1/runs/{run_id}/events", headers=AUTH) as response:
        body = "".join(response.iter_text())
    assert "event: run.retry" in body
    assert '"failure_kind": "transient"' in body
    assert "temporary" in body


def test_tool_call_disables_retry(client, settings):
    from app.agents.events import AgentEvent
    from app.agents.plugins import PLUGINS

    settings.run_retry_backoff_seconds = 0

    async def tool_then_fail(prompt, llm_config, max_steps):
        yield AgentEvent("tool.call", {"tool": "calculator", "input": {}})
        raise TransientError("after tool")

    PLUGINS["retry-tool-test"] = tool_then_fail
    try:
        agent = _published(
            client,
            slug="retry-tool-agent",
            kind="plugin",
            plugin_name="retry-tool-test",
            limits={"max_steps": 8, "timeout_seconds": 30, "max_attempts": 3},
        )
        run_id = client.post(
            "/v1/runs", json={"agent_id": agent["slug"], "input": "hi"}, headers=AUTH
        ).json()["run_id"]
        assert _wait_status(client, run_id, {"failed"}) == "failed"
        run = client.get(f"/v1/runs/{run_id}", headers=AUTH).json()
        assert run["attempts"] == 1
        assert run["failure_kind"] == "tool"
    finally:
        PLUGINS.pop("retry-tool-test", None)


def test_final_transient_failure_uses_all_attempts(client, settings, fake_graph):
    settings.run_retry_backoff_seconds = 0
    fake_graph(failures=[TransientError("one"), TransientError("two")])
    agent = _published(client, slug="retry-fail-agent")
    run_id = client.post(
        "/v1/runs", json={"agent_id": agent["slug"], "input": "hi"}, headers=AUTH
    ).json()["run_id"]
    assert _wait_status(client, run_id, {"failed"}) == "failed"
    run = client.get(f"/v1/runs/{run_id}", headers=AUTH).json()
    assert run["attempts"] == 2
    assert run["failure_kind"] == "transient"
    assert "two" in run["error"]


def test_fallback_model_used_on_retry(db, settings, monkeypatch, fake_graph):
    from app.agents import execution
    from app.main import create_app
    from app.settings import Settings, get_settings

    monkeypatch.setenv("RUN_RETRY_BACKOFF_SECONDS", "0")
    monkeypatch.setenv("RUN_FALLBACK_MODEL", "fallback-model")
    get_settings.cache_clear()
    app_settings = Settings(_env_file=None)
    seen: list[str | None] = []

    def capture_llm(agent_llm, run_override):
        seen.append(run_override.model if run_override is not None else None)
        return object()

    fake_graph(failures=[TransientError("temporary")])
    monkeypatch.setattr(execution, "build_llm", capture_llm)
    with TestClient(create_app(app_settings)) as client:
        agent = _published(client, slug="retry-fallback-agent")
        run_id = client.post(
            "/v1/runs", json={"agent_id": agent["slug"], "input": "hi"}, headers=AUTH
        ).json()["run_id"]
        assert _wait_status(client, run_id, {"succeeded"}) == "succeeded"
        run = client.get(f"/v1/runs/{run_id}", headers=AUTH).json()
        assert run["attempts"] == 2
    assert seen == [None, "fallback-model"]
