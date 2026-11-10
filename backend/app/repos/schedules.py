"""Cron schedules: persistence and next-run calculation."""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from typing import Any
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RunScheduleRow, utcnow
from app.runtime.models import ScheduleOut


def validate_cron(cron: str, tz_name: str) -> None:
    if not croniter.is_valid(cron):
        raise ValueError(f"invalid cron expression: {cron!r}")
    ZoneInfo(tz_name)


def next_run(cron: str, tz_name: str, base: datetime | None = None) -> datetime:
    zone = ZoneInfo(tz_name)
    current = (base or utcnow()).astimezone(zone)
    value = croniter(cron, current).get_next(datetime)
    return value.astimezone(dt_timezone.utc)


def to_out(row: RunScheduleRow) -> ScheduleOut:
    return ScheduleOut(
        id=row.id,
        name=row.name,
        agent_slug=row.agent_slug,
        input=row.input,
        cron=row.cron,
        timezone=row.timezone,
        enabled=row.enabled,
        next_run_at=row.next_run_at,
        last_run_at=row.last_run_at,
        last_run_id=row.last_run_id,
        last_error=row.last_error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def list_schedules(session: AsyncSession, p) -> list[RunScheduleRow]:
    stmt = select(RunScheduleRow)
    if not p.is_superadmin:
        stmt = stmt.where(
            RunScheduleRow.principal_kind == p.kind,
            RunScheduleRow.principal_id == p.id,
        )
    stmt = stmt.order_by(RunScheduleRow.created_at.desc())
    return list((await session.execute(stmt)).scalars())


async def get_schedule(
    session: AsyncSession, schedule_id: str
) -> RunScheduleRow | None:
    return await session.get(RunScheduleRow, schedule_id)


async def create_schedule(
    session: AsyncSession,
    *,
    name: str,
    agent_slug: str,
    input_value: Any,
    cron: str,
    tz_name: str,
    enabled: bool,
    p,
) -> RunScheduleRow:
    validate_cron(cron, tz_name)
    row = RunScheduleRow(
        name=name,
        agent_slug=agent_slug,
        input=input_value,
        cron=cron,
        timezone=tz_name,
        enabled=enabled,
        principal_kind=p.kind,
        principal_id=p.id,
        tenant_id=p.tenant_id,
        next_run_at=next_run(cron, tz_name) if enabled else None,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def update_schedule(
    session: AsyncSession,
    row: RunScheduleRow,
    *,
    name: str | None = None,
    agent_slug: str | None = None,
    input_value: Any = None,
    cron: str | None = None,
    tz_name: str | None = None,
    enabled: bool | None = None,
) -> RunScheduleRow:
    if name is not None:
        row.name = name
    if agent_slug is not None:
        row.agent_slug = agent_slug
    if input_value is not None:
        row.input = input_value
    if cron is not None:
        row.cron = cron
    if tz_name is not None:
        row.timezone = tz_name
    if cron is not None or tz_name is not None:
        validate_cron(row.cron, row.timezone)
    if enabled is not None:
        row.enabled = enabled
    row.next_run_at = (
        next_run(row.cron, row.timezone) if row.enabled else None
    )
    await session.commit()
    await session.refresh(row)
    return row
