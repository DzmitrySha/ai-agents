"""Notification channels and delivery outbox."""

from __future__ import annotations

import time
from datetime import timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from tests.conftest import AUTH

CHANNEL = {
    "name": "ops webhook",
    "kind": "webhook",
    "url": "https://example.com/hook",
    "secret": "s3cr3t",
    "enabled": True,
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
    raise AssertionError(f"run {run_id} stayed {status!r}")


def _agent(client: TestClient) -> None:
    created = client.post(
        "/v1/agents",
        json={"slug": "notify-agent", "name": "Notify", "system_prompt": "hi"},
        headers=AUTH,
    )
    assert created.status_code == 201, created.text
    assert (
        client.post(
            "/v1/agents/notify-agent/publish",
            json={"visibility": "shared"},
            headers=AUTH,
        ).status_code
        == 200
    )


def test_channel_crud(client):
    created = client.post("/api/admin/notification-channels", json=CHANNEL, headers=AUTH)
    assert created.status_code == 201, created.text
    channel = created.json()
    assert channel["secret_configured"] is True
    assert "s3cr3t" not in str(channel)

    listed = client.get("/api/admin/notification-channels", headers=AUTH).json()
    assert len(listed) == 1

    patched = client.patch(
        f"/api/admin/notification-channels/{channel['id']}",
        json={"enabled": False},
        headers=AUTH,
    )
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False

    deleted = client.delete(
        f"/api/admin/notification-channels/{channel['id']}", headers=AUTH
    )
    assert deleted.status_code == 204


def test_run_terminal_enqueues_and_sends(client, settings, fake_graph, monkeypatch):
    from app.db import get_session_factory
    from app.runtime import delivery
    from app.runtime.models import utcnow

    fake_graph()
    _agent(client)
    assert (
        client.post("/api/admin/notification-channels", json=CHANNEL, headers=AUTH).status_code
        == 201
    )
    run_id = client.post(
        "/v1/runs", json={"agent_id": "notify-agent", "input": "hi"}, headers=AUTH
    ).json()["run_id"]
    assert _wait_status(client, run_id, {"succeeded"}) == "succeeded"

    deadline = time.time() + 5
    deliveries = []
    while time.time() < deadline:
        deliveries = client.get("/api/admin/deliveries", headers=AUTH).json()["items"]
        if deliveries:
            break
        time.sleep(0.02)
    assert len(deliveries) == 1
    assert deliveries[0]["status"] == "pending"

    async def _ok(channel, run, settings):
        return None

    monkeypatch.setattr(delivery, "_deliver", _ok)
    session_factory = get_session_factory()

    async def tick():
        return await delivery.run_delivery_queue(
            session_factory, settings, now=utcnow()
        )

    assert client.portal.call(tick) == 1
    sent = client.get("/api/admin/deliveries", headers=AUTH).json()["items"][0]
    assert sent["status"] == "sent"
    assert sent["sent_at"]


def test_delivery_retries_then_fails(client, settings, monkeypatch):
    from app.db import get_session_factory
    from app.models import DeliveryRow, NotificationChannelRow, RunRow, utcnow
    from app.runtime import delivery

    settings.run_delivery_max_attempts = 2
    session_factory = get_session_factory()

    async def seed():
        async with session_factory() as session:
            channel = NotificationChannelRow(
                id="channel-1",
                name="hook",
                kind="webhook",
                url="https://example.com/hook",
                enabled=True,
                created_by="test",
            )
            run = RunRow(
                id="run-1",
                agent_slug="notify-agent",
                status="succeeded",
                input="hi",
                output="ok",
                principal_kind="service",
                principal_id="env",
            )
            session.add_all([channel, run])
            await session.commit()
            session.add(
                DeliveryRow(
                    id="delivery-1",
                    run_id="run-1",
                    channel_id="channel-1",
                    status="pending",
                    attempts=0,
                    next_attempt_at=utcnow(),
                )
            )
            await session.commit()

    async def _fail(channel, run, settings):
        raise RuntimeError("boom")

    monkeypatch.setattr(delivery, "_deliver", _fail)
    client.portal.call(seed)
    now = utcnow()

    async def tick(at):
        return await delivery.run_delivery_queue(session_factory, settings, now=at)

    assert client.portal.call(tick, now) == 1

    async def state():
        async with session_factory() as session:
            row = await session.get(DeliveryRow, "delivery-1")
            assert row is not None
            return row.status, row.attempts, row.next_attempt_at

    status, attempts, next_at = client.portal.call(state)
    assert status == "pending"
    assert attempts == 1
    assert next_at is not None

    client.portal.call(tick, now + timedelta(seconds=30))
    status, attempts, _ = client.portal.call(state)
    assert status == "failed"
    assert attempts == 2


def test_webhook_signature(monkeypatch):
    import asyncio

    from app.runtime import delivery

    captured = {}

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, content=None, headers=None):
            captured["url"] = url
            captured["content"] = content
            captured["headers"] = headers
            return SimpleNamespace(status_code=200, text="ok")

    monkeypatch.setattr(delivery.httpx, "AsyncClient", Client)
    channel = SimpleNamespace(url="https://example.com/hook", secret="s3cr3t")
    run = SimpleNamespace(
        id="run-1",
        agent_slug="agent",
        status="succeeded",
        output="ok",
        error=None,
        failure_kind=None,
        finished_at=None,
    )
    asyncio.run(delivery._send_webhook(channel, run))
    assert captured["url"] == "https://example.com/hook"
    assert captured["headers"]["X-Ai-Agents-Signature"].startswith("sha256=")
    assert b"secret" not in captured["content"]
