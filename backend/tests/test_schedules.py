"""Cron schedules: CRUD, run-now, due loop and idempotency."""

from __future__ import annotations

import time
from datetime import timedelta

from fastapi.testclient import TestClient

from tests.conftest import AUTH

from app.repos.auth import aware

AGENT = {
    "slug": "schedule-agent",
    "name": "Schedule",
    "system_prompt": "hi",
}
SCHEDULE = {
    "name": "every five",
    "agent_slug": "schedule-agent",
    "input": "hi",
    "cron": "*/5 * * * *",
    "timezone": "UTC",
    "enabled": True,
}


def _published(client: TestClient) -> None:
    created = client.post("/v1/agents", json=AGENT, headers=AUTH)
    assert created.status_code == 201, created.text
    published = client.post(
        "/v1/agents/schedule-agent/publish",
        json={"visibility": "shared"},
        headers=AUTH,
    )
    assert published.status_code == 200, published.text


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


def test_next_run_and_validation():
    from app.repos.schedules import next_run, validate_cron

    value = next_run("*/5 * * * *", "UTC")
    assert value.minute % 5 == 0
    validate_cron("0 9 * * 1-5", "Europe/Minsk")
    import pytest

    with pytest.raises(ValueError):
        validate_cron("not a cron", "UTC")
    with pytest.raises(Exception):
        validate_cron("* * * * *", "No/SuchZone")


def test_schedule_crud_and_run_now(client, fake_graph):
    fake_graph()
    _published(client)
    created = client.post("/v1/schedules", json=SCHEDULE, headers=AUTH)
    assert created.status_code == 201, created.text
    schedule = created.json()
    assert schedule["next_run_at"]
    assert schedule["enabled"] is True

    listed = client.get("/v1/schedules", headers=AUTH).json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == schedule["id"]

    disabled = client.patch(
        f"/v1/schedules/{schedule['id']}",
        json={"enabled": False},
        headers=AUTH,
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["next_run_at"] is None

    run = client.post(f"/v1/schedules/{schedule['id']}/run-now", headers=AUTH)
    assert run.status_code == 409

    enabled = client.patch(
        f"/v1/schedules/{schedule['id']}",
        json={"enabled": True},
        headers=AUTH,
    )
    assert enabled.status_code == 200
    assert enabled.json()["next_run_at"]

    run = client.post(f"/v1/schedules/{schedule['id']}/run-now", headers=AUTH)
    assert run.status_code == 201, run.text
    run_id = run.json()["run_id"]
    assert _wait_status(client, run_id, {"succeeded"}) == "succeeded"

    current = client.get(f"/v1/schedules/{schedule['id']}", headers=AUTH).json()
    assert current["last_run_id"] == run_id

    deleted = client.delete(f"/v1/schedules/{schedule['id']}", headers=AUTH)
    assert deleted.status_code == 204
    assert client.get("/v1/schedules", headers=AUTH).json()["total"] == 0


def test_invalid_cron_is_422(client):
    _published(client)
    response = client.post(
        "/v1/schedules", json={**SCHEDULE, "cron": "bad"}, headers=AUTH
    )
    assert response.status_code == 422


def test_due_loop_creates_one_run_for_slot(client, settings, fake_graph):
    from app.db import get_session_factory
    from app.models import RunScheduleRow, utcnow
    from app.runtime.scheduler import run_due_schedules

    fake_graph()
    _published(client)
    schedule = client.post("/v1/schedules", json=SCHEDULE, headers=AUTH).json()
    session_factory = get_session_factory()
    now = utcnow()

    async def make_due() -> None:
        async with session_factory() as session:
            row = await session.get(RunScheduleRow, schedule["id"])
            assert row is not None
            row.next_run_at = now - timedelta(seconds=1)
            await session.commit()

    async def tick() -> int:
        return await run_due_schedules(
            session_factory,
            client.app.state.run_manager,
            settings,
            now=now,
        )

    client.portal.call(make_due)
    assert client.portal.call(tick) == 1

    async def state():
        async with session_factory() as session:
            row = await session.get(RunScheduleRow, schedule["id"])
            assert row is not None
            return row.last_run_id, row.next_run_at

    run_id, next_at = client.portal.call(state)
    assert run_id
    assert next_at is not None and aware(next_at) > now
    assert _wait_status(client, run_id, {"succeeded"}) == "succeeded"

    client.portal.call(make_due)
    client.portal.call(tick)

    async def same_run():
        async with session_factory() as session:
            row = await session.get(RunScheduleRow, schedule["id"])
            assert row is not None
            return row.last_run_id

    assert client.portal.call(same_run) == run_id
