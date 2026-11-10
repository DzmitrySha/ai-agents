"""Notification channels and delivery records."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DeliveryRow, NotificationChannelRow
from app.runtime.models import DeliveryOut, NotificationChannelOut


def channel_out(row: NotificationChannelRow) -> NotificationChannelOut:
    return NotificationChannelOut(
        id=row.id,
        name=row.name,
        kind=row.kind,
        url=row.url,
        chat_id=row.chat_id,
        enabled=row.enabled,
        secret_configured=bool(row.secret),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def delivery_out(row: DeliveryRow) -> DeliveryOut:
    return DeliveryOut(
        id=row.id,
        run_id=row.run_id,
        channel_id=row.channel_id,
        status=row.status,
        attempts=row.attempts,
        next_attempt_at=row.next_attempt_at,
        last_error=row.last_error,
        created_at=row.created_at,
        sent_at=row.sent_at,
    )


async def list_channels(session: AsyncSession) -> list[NotificationChannelRow]:
    stmt = select(NotificationChannelRow).order_by(NotificationChannelRow.name)
    return list((await session.execute(stmt)).scalars())


async def get_channel(
    session: AsyncSession, channel_id: str
) -> NotificationChannelRow | None:
    return await session.get(NotificationChannelRow, channel_id)


async def create_channel(
    session: AsyncSession,
    *,
    name: str,
    kind: str,
    url: str | None,
    secret: str | None,
    chat_id: str | None,
    enabled: bool,
    created_by: str,
) -> NotificationChannelRow:
    row = NotificationChannelRow(
        name=name,
        kind=kind,
        url=url,
        secret=secret,
        chat_id=chat_id,
        enabled=enabled,
        created_by=created_by,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def update_channel(
    session: AsyncSession,
    row: NotificationChannelRow,
    **fields,
) -> NotificationChannelRow:
    for key, value in fields.items():
        if value is not None:
            setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    return row


async def list_deliveries(
    session: AsyncSession, *, limit: int = 50
) -> list[DeliveryRow]:
    stmt = (
        select(DeliveryRow)
        .order_by(DeliveryRow.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars())
