"""Usage analytics: middleware recording plus `/v1/stats/overview` aggregates."""

from __future__ import annotations

import time
from datetime import timedelta

from tests.conftest import AUTH


def _seed(run_db) -> None:
    """Two runs (1 ok / 1 failed), a tool call and two API calls in the window."""

    async def _insert() -> None:
        from app.db import get_session_factory
        from app.models import RunRow, UsageEvent, utcnow

        now = utcnow()
        async with get_session_factory()() as session:
            session.add_all(
                [
                    RunRow(
                        id="r-ok",
                        agent_slug="calc",
                        status="succeeded",
                        input="1+1",
                        principal_kind="service",
                        principal_id="env",
                        created_at=now - timedelta(hours=2),
                        started_at=now - timedelta(hours=2),
                        finished_at=now - timedelta(hours=2) + timedelta(seconds=2),
                    ),
                    RunRow(
                        id="r-fail",
                        agent_slug="calc",
                        status="failed",
                        input="boom",
                        principal_kind="service",
                        principal_id="env",
                        created_at=now - timedelta(days=1),
                        started_at=now - timedelta(days=1),
                        finished_at=now - timedelta(days=1) + timedelta(seconds=1),
                    ),
                    UsageEvent(kind="tool", tool_slug="calculator", agent_slug="calc"),
                    UsageEvent(
                        kind="api",
                        method="GET",
                        path="/v1/agents",
                        status_code=200,
                        duration_ms=10,
                    ),
                    UsageEvent(
                        kind="api",
                        method="POST",
                        path="/v1/runs",
                        status_code=500,
                        duration_ms=90,
                    ),
                ]
            )
            await session.commit()

    run_db(_insert)


def test_overview_aggregates_every_kind(client, run_db):
    _seed(run_db)

    response = client.get("/v1/stats/overview?days=7", headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["days"] == 7
    assert body["runs_total"] == 2
    assert body["runs_succeeded"] == 1
    assert body["success_rate"] == 0.5
    assert len(body["runs_daily"]) == 7
    assert sum(point["succeeded"] for point in body["runs_daily"]) == 1
    assert sum(point["failed"] for point in body["runs_daily"]) == 1

    assert body["tools_total"] == 1
    assert body["top_tools"] == [{"slug": "calculator", "calls": 1}]

    assert body["api_total"] == 2
    assert body["api_errors"] == 1
    assert body["api_latency"]["p50_ms"] == 10
    assert body["api_latency"]["p95_ms"] == 90
    paths = {(item["method"], item["path"]) for item in body["top_endpoints"]}
    assert paths == {("GET", "/v1/agents"), ("POST", "/v1/runs")}

    agent = body["top_agents"][0]
    assert agent["slug"] == "calc"
    assert agent["runs"] == 2
    assert agent["succeeded"] == 1
    assert agent["failed"] == 1
    assert agent["success_rate"] == 0.5
    assert agent["avg_duration_ms"] == 1500


def test_overview_validates_window(client):
    assert client.get("/v1/stats/overview?days=0", headers=AUTH).status_code == 422
    assert client.get("/v1/stats/overview?days=1000", headers=AUTH).status_code == 422


def test_overview_requires_runs_read(client, login):
    admin = login("root", is_superadmin=True)
    created = client.post(
        "/api/admin/service-keys",
        headers=admin,
        json={"name": "agents-only", "scopes": ["agents:read"]},
    ).json()
    bearer = {"Authorization": f"Bearer {created['key']}"}

    assert client.get("/v1/stats/overview", headers=bearer).status_code == 403
    client.cookies.clear()
    assert client.get("/v1/stats/overview").status_code == 401


def test_middleware_records_api_calls(client, run_db):
    assert client.get("/v1/agents", headers=AUTH).status_code == 200

    def _count() -> int:
        async def _query() -> int:
            from sqlalchemy import func, select

            from app.db import get_session_factory
            from app.models import UsageEvent

            async with get_session_factory()() as session:
                return int(
                    (
                        await session.execute(
                            select(func.count())
                            .select_from(UsageEvent)
                            .where(UsageEvent.kind == "api")
                        )
                    ).scalar_one()
                )

        return run_db(_query)

    for _ in range(40):
        if _count() > 0:
            break
        time.sleep(0.05)

    async def _row():
        from sqlalchemy import select

        from app.db import get_session_factory
        from app.models import UsageEvent

        async with get_session_factory()() as session:
            return (
                await session.execute(
                    select(UsageEvent).where(UsageEvent.kind == "api")
                )
            ).scalars().first()

    row = run_db(_row)
    assert row is not None
    assert row.path == "/v1/agents"
    assert row.status_code == 200
    assert row.principal_kind == "service"


def test_normalize_path_groups_instance_ids():
    from app.runtime.usage_asgi import normalize_path

    assert normalize_path("/v1/runs/0e77da9c-5dd8-4174-b83a-091e40327286") == "/v1/runs/{id}"
    assert normalize_path("/v1/runs/0e77da9c-5dd8-4174-b83a-091e40327286/events") == (
        "/v1/runs/{id}/events"
    )
    assert normalize_path("/v1/items/42") == "/v1/items/{n}"
    assert normalize_path("/v1/agents") == "/v1/agents"
