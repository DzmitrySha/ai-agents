"""Retention for run events: archive the digest, then drop raw events."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select

from app.logging_setup import logger
from app.models import RunEventRow, RunRow, utcnow
from app.repos.runs import load_run_events
from app.runtime.digest import build_digest
from app.runtime.models import TERMINAL_STATUSES

BATCH_SIZE = 200
_last_run_at: datetime | None = None


def last_retention_at() -> datetime | None:
    return _last_run_at


async def prune_run_events(
    session_factory: Any,
    settings: Any,
    *,
    now: datetime | None = None,
) -> int:
    """Delete expired events for terminal runs, preserving their digest.

    ``RUN_EVENTS_RETENTION_DAYS=0`` disables pruning. Runs whose digest cannot
    be stored are skipped so raw events are never lost.
    """
    days = int(settings.run_events_retention_days)
    if days <= 0:
        return 0
    archived_at = now or utcnow()
    cutoff = archived_at - timedelta(days=days)
    processed = 0

    while True:
        async with session_factory() as session:
            stmt = (
                select(RunRow.id)
                .where(
                    RunRow.status.in_(tuple(TERMINAL_STATUSES)),
                    RunRow.finished_at.is_not(None),
                    RunRow.finished_at < cutoff,
                    RunRow.events_archived_at.is_(None),
                )
                .order_by(RunRow.finished_at)
                .limit(BATCH_SIZE)
            )
            run_ids = list((await session.execute(stmt)).scalars())

        if not run_ids:
            break
        batch_progress = 0
        for run_id in run_ids:
            try:
                async with session_factory() as session:
                    row = await session.get(RunRow, run_id)
                    if row is None or row.events_archived_at is not None:
                        continue
                    events = await load_run_events(session, run_id)
                    if row.digest is None:
                        row.digest = build_digest(row, events)
                    if events:
                        await session.execute(
                            delete(RunEventRow).where(RunEventRow.run_id == run_id)
                        )
                    row.events_archived_at = archived_at
                    await session.commit()
                processed += 1
                batch_progress += 1
            except Exception as exc:  # noqa: BLE001 - one bad run must not stop retention
                logger.warning("retention skipped run {}: {}", run_id, exc)
        if batch_progress == 0:
            break
    return processed


async def retention_loop(session_factory: Any, settings: Any) -> None:
    global _last_run_at
    while True:
        try:
            await prune_run_events(session_factory, settings)
            _last_run_at = utcnow()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            logger.warning("run event retention failed: {}", exc)
        await asyncio.sleep(max(60, int(settings.run_retention_interval_seconds)))
