"""Run + run-event persistence and visibility."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import Principal
from app.models import Agent, AgentVersion, RunEventRow, RunRow, UserIdentity, utcnow
from app.repos.approvals import expire_pending
from app.runtime.models import (
    TERMINAL_STATUSES,
    CreateRunRequest,
    RunOut,
    RunStatus,
)


class DailyQuotaExceeded(Exception):
    """Raised when a role=user principal exceeds the daily run limit."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"daily run limit exceeded ({limit} per day)")


class DailyTokenBudgetExceeded(Exception):
    """Raised when a role=user principal exceeds the daily token budget."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"daily token budget exceeded ({limit} per day)")


class IdempotencyConflict(Exception):
    """A concurrent insert won the idempotency race; replay the existing run."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"idempotency key already used by run {run_id}")


def _prompt_from_input(value: str | dict[str, Any] | list[Any]) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def prompt_for(request: CreateRunRequest) -> str:
    return _prompt_from_input(request.input)


async def count_runs_since(
    session: AsyncSession,
    *,
    principal_kind: str,
    principal_id: str,
    since: datetime,
) -> int:
    stmt = (
        select(func.count())
        .select_from(RunRow)
        .where(
            RunRow.principal_kind == principal_kind,
            RunRow.principal_id == principal_id,
            RunRow.created_at >= since,
        )
    )
    return int((await session.execute(stmt)).scalar_one())


def can_view_run(run: RunRow, agent: Agent | None, p: Principal) -> bool:
    if p.is_superadmin:
        return True
    if run.principal_kind == p.kind and run.principal_id == p.id:
        return True
    return (
        p.kind == "user"
        and agent is not None
        and agent.owner_kind == "user"
        and agent.owner_id == p.id
    )


async def assert_daily_quota(
    session: AsyncSession,
    *,
    p: Principal,
    limit: int,
) -> None:
    """Lock the user row (when present) and ensure today's run count is under ``limit``.

    Must run in the same transaction that inserts the new run row so concurrent
    creates cannot both pass the check.
    """
    if p.kind == "user" and p.id:
        await session.execute(
            select(UserIdentity.sub)
            .where(UserIdentity.sub == p.id)
            .with_for_update()
        )
    since = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    used = await count_runs_since(
        session,
        principal_kind=p.kind,
        principal_id=p.id,
        since=since,
    )
    if used >= limit:
        raise DailyQuotaExceeded(limit)


async def tokens_since(
    session: AsyncSession,
    *,
    principal_kind: str,
    principal_id: str,
    since: datetime,
) -> int:
    stmt = select(func.coalesce(func.sum(RunRow.total_tokens), 0)).where(
        RunRow.principal_kind == principal_kind,
        RunRow.principal_id == principal_id,
        RunRow.finished_at.is_not(None),
        RunRow.finished_at >= since,
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def assert_daily_token_budget(
    session: AsyncSession,
    *,
    p: Principal,
    limit: int,
) -> None:
    """Lock the user row and ensure today's token usage is under ``limit``."""
    if p.kind != "user" or not p.id:
        return
    await session.execute(
        select(UserIdentity.sub).where(UserIdentity.sub == p.id).with_for_update()
    )
    since = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    used = await tokens_since(
        session,
        principal_kind=p.kind,
        principal_id=p.id,
        since=since,
    )
    if used >= limit:
        raise DailyTokenBudgetExceeded(limit)


async def count_queued_runs(session: AsyncSession) -> int:
    stmt = select(func.count()).select_from(RunRow).where(
        RunRow.status == RunStatus.queued.value
    )
    return int((await session.execute(stmt)).scalar_one())


async def oldest_queued_at(session: AsyncSession) -> datetime | None:
    stmt = select(func.min(RunRow.created_at)).where(
        RunRow.status == RunStatus.queued.value
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_run_by_idempotency(
    session: AsyncSession,
    *,
    principal_kind: str,
    principal_id: str,
    key: str,
) -> RunRow | None:
    stmt = select(RunRow).where(
        RunRow.principal_kind == principal_kind,
        RunRow.principal_id == principal_id,
        RunRow.idempotency_key == key,
    )
    return (await session.execute(stmt)).scalars().first()


async def create_run_row(
    session: AsyncSession,
    *,
    agent: Agent,
    version: AgentVersion,
    p: Principal,
    request: CreateRunRequest,
    daily_limit: int | None = None,
    harness_snapshot: dict[str, Any] | None = None,
    harness_hash: str | None = None,
    idempotency_key: str | None = None,
    parent_run_id: str | None = None,
    depth: int = 0,
) -> RunRow:
    if daily_limit is not None:
        await assert_daily_quota(session, p=p, limit=daily_limit)
    row = RunRow(
        agent_id=agent.id,
        agent_version_id=version.id,
        agent_slug=agent.slug,
        status=RunStatus.queued.value,
        input=request.input,
        run_metadata=request.metadata,
        harness_snapshot=harness_snapshot,
        harness_hash=harness_hash,
        idempotency_key=idempotency_key,
        parent_run_id=parent_run_id,
        depth=depth,
        principal_kind=p.kind,
        principal_id=p.id,
        tenant_id=p.tenant_id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_run_row(session: AsyncSession, run_id: str) -> RunRow | None:
    return await session.get(RunRow, run_id)


async def get_agent_for_run(session: AsyncSession, run: RunRow) -> Agent | None:
    if not run.agent_id:
        return None
    return await session.get(Agent, run.agent_id)


async def count_child_runs(session: AsyncSession, parent_run_id: str) -> int:
    stmt = (
        select(func.count())
        .select_from(RunRow)
        .where(RunRow.parent_run_id == parent_run_id)
    )
    return int((await session.execute(stmt)).scalar_one())


async def list_child_runs(
    session: AsyncSession, parent_run_id: str
) -> list[RunRow]:
    stmt = (
        select(RunRow)
        .where(RunRow.parent_run_id == parent_run_id)
        .order_by(RunRow.created_at)
    )
    return list((await session.execute(stmt)).scalars())


async def list_run_rows(
    session: AsyncSession,
    p: Principal,
    *,
    status: str | None,
    agent_id: str | None,
    limit: int,
    offset: int,
    parent_run_id: str | None = None,
) -> tuple[list[RunRow], int]:
    stmt = select(RunRow)
    if not p.is_superadmin:
        owned_agents = select(Agent.id).where(
            Agent.owner_kind == "user", Agent.owner_id == p.id
        )
        stmt = stmt.where(
            or_(
                and_(
                    RunRow.principal_kind == p.kind,
                    RunRow.principal_id == p.id,
                ),
                RunRow.agent_id.in_(owned_agents),
            )
        )
    if status:
        stmt = stmt.where(RunRow.status == status)
    if agent_id:
        stmt = stmt.where(
            or_(RunRow.agent_id == agent_id, RunRow.agent_slug == agent_id)
        )
    if parent_run_id:
        stmt = stmt.where(RunRow.parent_run_id == parent_run_id)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    page = stmt.order_by(RunRow.created_at.desc()).limit(limit).offset(offset)
    return list((await session.execute(page)).scalars()), int(total)


async def _version_number(
    session: AsyncSession, version_id: str | None
) -> int | None:
    if not version_id:
        return None
    version = await session.get(AgentVersion, version_id)
    return version.version if version is not None else None


async def to_out(session: AsyncSession, run: RunRow) -> RunOut:
    return RunOut(
        run_id=run.id,
        agent_id=run.agent_slug,
        agent_version=await _version_number(session, run.agent_version_id),
        harness_hash=run.harness_hash,
        prompt_tokens=run.prompt_tokens,
        completion_tokens=run.completion_tokens,
        total_tokens=run.total_tokens,
        failure_kind=run.failure_kind,
        attempts=run.attempts,
        parent_run_id=run.parent_run_id,
        depth=run.depth,
        events_archived_at=run.events_archived_at,
        status=RunStatus(run.status),
        input=run.input,
        metadata=run.run_metadata,
        output=run.output,
        error=run.error,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


async def set_run_status(
    session: AsyncSession,
    run_id: str,
    status: RunStatus | str,
    *,
    output: str | None = None,
    error: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    failure_kind: str | None = None,
    attempts: int | None = None,
    commit: bool = True,
) -> RunRow | None:
    row = await session.get(RunRow, run_id)
    if row is None:
        return None
    value = status.value if isinstance(status, RunStatus) else status
    now = utcnow()
    row.status = value
    if value == RunStatus.running.value and row.started_at is None:
        row.started_at = now
    if value in TERMINAL_STATUSES:
        row.finished_at = now
    if output is not None:
        row.output = output
    if error is not None:
        row.error = error
    if prompt_tokens is not None:
        row.prompt_tokens = prompt_tokens
    if completion_tokens is not None:
        row.completion_tokens = completion_tokens
    if total_tokens is not None:
        row.total_tokens = total_tokens
    if failure_kind is not None:
        row.failure_kind = failure_kind
    if attempts is not None:
        row.attempts = attempts
    if commit:
        await session.commit()
        await session.refresh(row)
    return row


async def max_event_seq(session: AsyncSession, run_id: str) -> int:
    stmt = select(func.max(RunEventRow.seq)).where(RunEventRow.run_id == run_id)
    return int((await session.execute(stmt)).scalar_one_or_none() or 0)


async def append_run_event(
    session: AsyncSession,
    run_id: str,
    seq: int,
    event: str,
    data: dict[str, Any],
    *,
    commit: bool = True,
) -> RunEventRow:
    row = RunEventRow(run_id=run_id, seq=seq, event=event, data=data)
    session.add(row)
    if commit:
        await session.commit()
    return row


async def load_run_events(
    session: AsyncSession, run_id: str, *, after_seq: int = 0
) -> list[RunEventRow]:
    stmt = (
        select(RunEventRow)
        .where(RunEventRow.run_id == run_id, RunEventRow.seq > after_seq)
        .order_by(RunEventRow.seq)
    )
    return list((await session.execute(stmt)).scalars())


async def recover_stale_runs(session: AsyncSession) -> int:
    """Mark runs left running by a restart as failed and record run.failed."""
    stmt = select(RunRow).where(
        RunRow.status.in_(
            [
                RunStatus.queued.value,
                RunStatus.running.value,
                RunStatus.waiting_approval.value,
            ]
        )
    )
    rows = list((await session.execute(stmt)).scalars())
    for row in rows:
        now = utcnow()
        await expire_pending(session, row.id, resolved_by="server restarted")
        row.status = RunStatus.failed.value
        row.error = "server restarted"
        row.finished_at = now
        await session.commit()
        seq = await max_event_seq(session, row.id) + 1
        await append_run_event(
            session, row.id, seq, "run.failed", {"error": "server restarted"}
        )
    return len(rows)
