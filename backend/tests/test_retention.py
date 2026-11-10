"""Run event retention: digest persists, events disappear, transcript is 410."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from tests.conftest import AUTH

from sqlalchemy import select


def test_prune_archives_events_and_keeps_digest(client, settings):
    from app.db import get_session_factory
    from app.models import RunEventRow, RunRow, utcnow
    from app.runtime.retention import prune_run_events

    run_id = str(uuid4())
    now = utcnow()
    session_factory = get_session_factory()

    async def seed() -> None:
        async with session_factory() as session:
            session.add(
                RunRow(
                    id=run_id,
                    agent_slug="retention-agent",
                    status="succeeded",
                    input="hi",
                    output="ok",
                    principal_kind="service",
                    principal_id="env",
                    tenant_id="default",
                    started_at=now - timedelta(days=31, seconds=2),
                    finished_at=now - timedelta(days=31),
                )
            )
            await session.commit()
            for seq, event, data in (
                (1, "run.started", {"agent_id": "retention-agent"}),
                (2, "agent.step", {"node": "model"}),
                (3, "run.completed", {"output": "ok"}),
            ):
                session.add(
                    RunEventRow(run_id=run_id, seq=seq, event=event, data=data)
                )
            await session.commit()

    async def prune() -> int:
        return await prune_run_events(session_factory, settings, now=now)

    client.portal.call(seed)
    assert client.portal.call(prune) >= 1

    async def state() -> tuple[int, bool, bool]:
        async with session_factory() as session:
            row = await session.get(RunRow, run_id)
            assert row is not None
            events = (
                await session.execute(
                    select(RunEventRow).where(RunEventRow.run_id == run_id)
                )
            ).scalars().all()
            return len(events), row.digest is not None, row.events_archived_at is not None

    count, digest_saved, archived = client.portal.call(state)
    assert count == 0
    assert digest_saved
    assert archived

    digest = client.get(f"/v1/runs/{run_id}/digest", headers=AUTH)
    assert digest.status_code == 200, digest.text
    assert digest.json()["steps"] == 1
    assert digest.json()["total_tokens"] is None

    with client.stream("GET", f"/v1/runs/{run_id}/events", headers=AUTH) as response:
        body = "".join(response.iter_text())
    assert "event: run.completed" in body
    assert "event: run.started" not in body
    assert "event: agent.step" not in body

    transcript = client.get(f"/v1/runs/{run_id}/transcript", headers=AUTH)
    assert transcript.status_code == 410
    assert transcript.json()["detail"] == "transcript archived"
