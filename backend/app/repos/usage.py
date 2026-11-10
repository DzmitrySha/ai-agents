"""Usage analytics: append-only events plus in-process aggregation for charts.

Aggregation happens in Python so the same code works on PostgreSQL (prod) and
SQLite (tests); the control plane's volumes are small enough for that.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_setup import logger
from app.models import RunRow, UsageEvent
from app.repos.auth import aware
from app.runtime.models import (
    AgentUsage,
    ApiDailyPoint,
    EndpointUsage,
    LatencyStats,
    RunsDailyPoint,
    StatsOverview,
    ToolDailyPoint,
    ToolUsage,
    utcnow,
)

TRANSIENT_STATUSES = frozenset({"queued", "running"})
ERROR_STATUS = 400
RETENTION_DAYS = 180
TOP_LIMIT = 10


def _percentile(values: list[int], ratio: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(ratio * len(ordered)) - 1))
    return int(ordered[index])


def _day(value: datetime) -> str:
    return aware(value).date().isoformat()


async def record(
    session_factory,
    *,
    kind: str,
    agent_slug: str | None = None,
    tool_slug: str | None = None,
    run_id: str | None = None,
    principal_kind: str = "",
    principal_id: str = "",
    method: str | None = None,
    path: str | None = None,
    status_code: int | None = None,
    duration_ms: int | None = None,
) -> None:
    """Best-effort insert: analytics must never break the request/run it measures."""
    try:
        async with session_factory() as session:
            session.add(
                UsageEvent(
                    kind=kind,
                    agent_slug=agent_slug,
                    tool_slug=tool_slug,
                    run_id=run_id,
                    principal_kind=principal_kind,
                    principal_id=principal_id,
                    method=method,
                    path=(path or "")[:200] or None,
                    status_code=status_code,
                    duration_ms=duration_ms,
                )
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001 - swallow, log once per failure
        logger.warning("usage record failed ({}): {}", kind, exc)


async def purge(session: AsyncSession, days: int = RETENTION_DAYS) -> int:
    cutoff = utcnow() - timedelta(days=days)
    result = await session.execute(delete(UsageEvent).where(UsageEvent.ts < cutoff))
    await session.commit()
    return int(result.rowcount or 0)


async def overview(session: AsyncSession, days: int) -> StatsOverview:
    days = max(1, min(int(days), 90))
    today = utcnow().date()
    since = datetime.combine(today - timedelta(days=days - 1), datetime.min.time())
    dates = [(today - timedelta(days=days - 1 - offset)).isoformat() for offset in range(days)]

    runs_daily = {date: RunsDailyPoint(date=date) for date in dates}
    agents: dict[str, dict[str, Any]] = {}
    runs_total = runs_succeeded = 0
    tokens_total = 0

    run_rows = (
        await session.execute(
            select(
                RunRow.created_at,
                RunRow.status,
                RunRow.agent_slug,
                RunRow.started_at,
                RunRow.finished_at,
                RunRow.total_tokens,
            ).where(RunRow.created_at >= since)
        )
    ).all()
    for created_at, status, agent_slug, started_at, finished_at, total_tokens in run_rows:
        runs_total += 1
        tokens = int(total_tokens or 0)
        tokens_total += tokens
        point = runs_daily.get(_day(created_at))
        state = str(status)
        if point is not None:
            if state == "succeeded":
                point.succeeded += 1
            elif state == "failed":
                point.failed += 1
            elif state == "cancelled":
                point.cancelled += 1
            else:
                point.other += 1
        if state == "succeeded":
            runs_succeeded += 1
        slug = str(agent_slug or "")
        bucket = agents.setdefault(
            slug, {"runs": 0, "succeeded": 0, "failed": 0, "durations": [], "tokens": 0}
        )
        bucket["runs"] += 1
        bucket["tokens"] += tokens
        if state == "succeeded":
            bucket["succeeded"] += 1
        elif state == "failed":
            bucket["failed"] += 1
        if started_at is not None and finished_at is not None:
            elapsed = (aware(finished_at) - aware(started_at)).total_seconds() * 1000
            if elapsed >= 0:
                bucket["durations"].append(elapsed)

    queued_row = (
        await session.execute(
            select(func.count(), func.min(RunRow.created_at)).where(
                RunRow.status == "queued"
            )
        )
    ).one()
    queued_runs = int(queued_row[0] or 0)
    oldest_queued = queued_row[1]
    oldest_queued_seconds = (
        max(0, int((utcnow() - aware(oldest_queued)).total_seconds()))
        if oldest_queued is not None
        else None
    )

    tools_daily = {date: ToolDailyPoint(date=date) for date in dates}
    tools: dict[str, int] = {}
    tool_calls = 0
    tool_rows = (
        await session.execute(
            select(UsageEvent.ts, UsageEvent.tool_slug).where(
                UsageEvent.kind == "tool", UsageEvent.ts >= since
            )
        )
    ).all()
    for ts, tool_slug in tool_rows:
        tool_calls += 1
        point = tools_daily.get(_day(ts))
        if point is not None:
            point.calls += 1
        key = str(tool_slug or "")
        tools[key] = tools.get(key, 0) + 1

    api_daily = {date: ApiDailyPoint(date=date) for date in dates}
    api_total = api_errors = 0
    latencies: list[int] = []
    endpoints: dict[tuple[str, str], dict[str, Any]] = {}
    api_rows = (
        await session.execute(
            select(
                UsageEvent.ts,
                UsageEvent.method,
                UsageEvent.path,
                UsageEvent.status_code,
                UsageEvent.duration_ms,
            ).where(UsageEvent.kind == "api", UsageEvent.ts >= since)
        )
    ).all()
    for ts, method, path, status_code, duration_ms in api_rows:
        api_total += 1
        failed = status_code is not None and status_code >= ERROR_STATUS
        if failed:
            api_errors += 1
        point = api_daily.get(_day(ts))
        if point is not None:
            point.calls += 1
            if failed:
                point.errors += 1
        if duration_ms is not None:
            latencies.append(int(duration_ms))
        key = (str(method or ""), str(path or ""))
        bucket = endpoints.setdefault(key, {"calls": 0, "errors": 0, "durations": []})
        bucket["calls"] += 1
        if failed:
            bucket["errors"] += 1
        if duration_ms is not None:
            bucket["durations"].append(int(duration_ms))

    top_agents: list[AgentUsage] = []
    for slug, bucket in sorted(
        agents.items(), key=lambda item: item[1]["runs"], reverse=True
    )[:TOP_LIMIT]:
        durations = bucket["durations"]
        top_agents.append(
            AgentUsage(
                slug=slug,
                runs=bucket["runs"],
                succeeded=bucket["succeeded"],
                failed=bucket["failed"],
                success_rate=round(bucket["succeeded"] / bucket["runs"], 3)
                if bucket["runs"]
                else 0.0,
                avg_duration_ms=int(sum(durations) / len(durations)) if durations else None,
                tokens=bucket["tokens"],
            )
        )

    top_tools = [
        ToolUsage(slug=slug, calls=calls)
        for slug, calls in sorted(tools.items(), key=lambda item: item[1], reverse=True)[
            :TOP_LIMIT
        ]
    ]

    top_endpoints: list[EndpointUsage] = []
    for (method, path), bucket in sorted(
        endpoints.items(), key=lambda item: item[1]["calls"], reverse=True
    )[:TOP_LIMIT]:
        top_endpoints.append(
            EndpointUsage(
                method=method,
                path=path,
                calls=bucket["calls"],
                errors=bucket["errors"],
                p95_ms=_percentile(bucket["durations"], 0.95),
            )
        )

    return StatsOverview(
        days=days,
        since=since,
        runs_total=runs_total,
        runs_succeeded=runs_succeeded,
        success_rate=round(runs_succeeded / runs_total, 3) if runs_total else 0.0,
        runs_daily=[runs_daily[date] for date in dates],
        tokens_total=tokens_total,
        queued_runs=queued_runs,
        oldest_queued_seconds=oldest_queued_seconds,
        tools_total=tool_calls,
        tools_daily=[tools_daily[date] for date in dates],
        api_total=api_total,
        api_errors=api_errors,
        api_latency=LatencyStats(
            p50_ms=_percentile(latencies, 0.5), p95_ms=_percentile(latencies, 0.95)
        ),
        api_daily=[api_daily[date] for date in dates],
        top_agents=top_agents,
        top_tools=top_tools,
        top_endpoints=top_endpoints,
    )


_TASKS: set[Any] = set()


def spawn(session_factory, **fields: Any) -> None:
    """Fire-and-forget recording so hot paths (SSE, tool calls) never wait on it."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(record(session_factory, **fields))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
