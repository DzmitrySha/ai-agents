"""Cron scheduler loop for `/v1/schedules`."""

from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import (
    Principal,
    normalize_scopes,
    scopes_for_role,
    service_all_scopes,
)
from app.logging_setup import logger
from app.models import RunScheduleRow, ServiceKey, UserIdentity, utcnow
from app.redaction import redact_text
from app.repos.schedules import next_run
from app.runtime.models import CreateRunRequest
from app.settings import Settings


async def principal_for_schedule(
    session: AsyncSession, row: RunScheduleRow, settings: Settings
) -> Principal | None:
    if row.principal_kind == "user":
        user = await session.get(UserIdentity, row.principal_id)
        if user is None:
            return None
        role = "superadmin" if user.is_superadmin else (user.app_role or "user")
        return Principal(
            kind="user",
            id=user.sub,
            email=user.email,
            is_superadmin=user.is_superadmin,
            scopes=scopes_for_role(role),
            roles=tuple(user.roles or []),
            tenant_id=row.tenant_id,
            app_role=role,
            daily_run_limit=user.daily_run_limit,
        )
    if row.principal_kind == "service":
        if row.principal_id == "env":
            if not settings.service_key_set:
                return None
            return Principal(
                kind="service",
                id="env",
                is_superadmin=True,
                scopes=service_all_scopes(),
                tenant_id=row.tenant_id,
            )
        key = await session.get(ServiceKey, row.principal_id)
        if key is None or not key.enabled:
            return None
        scopes = normalize_scopes(key.scopes or [])
        return Principal(
            kind="service",
            id=key.id,
            is_superadmin="admin" in scopes,
            scopes=scopes,
            tenant_id=row.tenant_id,
            catalog_restricted=True,
            agent_slugs=tuple(key.agent_slugs or []),
            tool_slugs=tuple(key.tool_slugs or []),
            skill_slugs=tuple(key.skill_slugs or []),
        )
    return None


def _daily_limits(p: Principal, settings: Settings) -> tuple[int | None, int | None]:
    if p.is_superadmin or p.app_role != "user":
        return None, None
    run_limit = p.daily_run_limit
    if run_limit is None:
        run_limit = settings.user_daily_run_limit
    token_limit = settings.user_daily_token_limit
    return run_limit or None, token_limit or None


async def run_due_schedules(
    session_factory,
    manager,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> int:
    current = now or utcnow()
    async with session_factory() as session:
        stmt = (
            select(RunScheduleRow)
            .where(
                RunScheduleRow.enabled.is_(True),
                RunScheduleRow.next_run_at.is_not(None),
                RunScheduleRow.next_run_at <= current,
            )
            .order_by(RunScheduleRow.next_run_at)
            .limit(settings.run_schedule_max_per_tick)
            .with_for_update(skip_locked=True)
        )
        rows = list((await session.execute(stmt)).scalars())
    processed = 0
    for row in rows:
        async with session_factory() as session:
            current_row = await session.get(RunScheduleRow, row.id)
            if current_row is None or not current_row.enabled:
                continue
            principal = await principal_for_schedule(session, current_row, settings)
            if principal is None:
                current_row.enabled = False
                current_row.last_error = "schedule principal is unavailable"
                current_row.next_run_at = None
                await session.commit()
                continue
            slot = current_row.next_run_at or current
            current_row.last_run_at = slot
            current_row.next_run_at = next_run(
                current_row.cron, current_row.timezone, base=current
            )
            await session.commit()

            run_limit, token_limit = _daily_limits(principal, settings)
            try:
                out = await manager.create_run(
                    session_factory,
                    principal,
                    CreateRunRequest(
                        agent_id=current_row.agent_slug,
                        input=current_row.input,
                    ),
                    daily_limit=run_limit,
                    daily_token_limit=token_limit,
                    idempotency_key=f"schedule:{current_row.id}:{slot.isoformat()}",
                )
                current_row.last_run_id = out.run_id
                current_row.last_error = None
            except Exception as exc:  # noqa: BLE001 - one schedule must not stop the loop
                current_row.last_error = redact_text(
                    f"{type(exc).__name__}: {exc}"
                )[:2000]
            await session.commit()
            processed += 1
    return processed


async def schedule_loop(session_factory, manager, settings: Settings) -> None:
    while True:
        try:
            await run_due_schedules(session_factory, manager, settings)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            logger.warning("schedule loop failed: {}", exc)
        await asyncio.sleep(max(5, int(settings.run_schedule_poll_seconds)))
