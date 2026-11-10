"""Persistence for human approvals of mutating tool calls."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RunApprovalRow, utcnow


async def create_approval(
    session: AsyncSession,
    *,
    approval_id: str,
    run_id: str,
    tool: str,
    tool_input: dict[str, Any],
) -> RunApprovalRow:
    row = RunApprovalRow(
        id=approval_id,
        run_id=run_id,
        tool=tool,
        input=tool_input,
        status="pending",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_approval(
    session: AsyncSession, approval_id: str
) -> RunApprovalRow | None:
    return await session.get(RunApprovalRow, approval_id)


async def list_approvals(
    session: AsyncSession, run_id: str
) -> list[RunApprovalRow]:
    stmt = (
        select(RunApprovalRow)
        .where(RunApprovalRow.run_id == run_id)
        .order_by(RunApprovalRow.requested_at)
    )
    return list((await session.execute(stmt)).scalars())


async def resolve_approval(
    session: AsyncSession,
    approval_id: str,
    *,
    status: str,
    resolved_by: str,
    resolved_at: datetime | None = None,
) -> RunApprovalRow | None:
    row = await get_approval(session, approval_id)
    if row is None:
        return None
    row.status = status
    row.resolved_at = resolved_at or utcnow()
    row.resolved_by = resolved_by
    await session.commit()
    await session.refresh(row)
    return row


async def expire_pending(
    session: AsyncSession, run_id: str, *, resolved_by: str = "system"
) -> int:
    stmt = select(RunApprovalRow).where(
        RunApprovalRow.run_id == run_id,
        RunApprovalRow.status == "pending",
    )
    rows = list((await session.execute(stmt)).scalars())
    now = utcnow()
    for row in rows:
        row.status = "expired"
        row.resolved_at = now
        row.resolved_by = resolved_by
    if rows:
        await session.commit()
    return len(rows)


async def pending_count(session: AsyncSession) -> int:
    stmt = (
        select(func.count())
        .select_from(RunApprovalRow)
        .where(RunApprovalRow.status == "pending")
    )
    return int((await session.execute(stmt)).scalar_one())
