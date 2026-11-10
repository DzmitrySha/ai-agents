"""Admin API for notification channels and delivery log."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.deps import SessionDep, require_csrf, require_scope
from app.auth.principal import Principal
from app.repos import notifications as notifications_repo
from app.runtime.models import (
    DeliveryList,
    NotificationChannelCreate,
    NotificationChannelOut,
    NotificationChannelUpdate,
)

router = APIRouter(
    prefix="/api/admin",
    tags=["notifications"],
    dependencies=[Depends(require_csrf)],
)


def _validate(payload: NotificationChannelCreate) -> None:
    if payload.kind == "webhook" and not (payload.url or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="webhook URL is required"
        )
    if payload.kind == "telegram" and not (payload.chat_id or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="telegram chat_id is required"
        )


@router.get("/notification-channels", response_model=list[NotificationChannelOut])
async def list_channels(
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_scope("admin"))],
) -> list[NotificationChannelOut]:
    return [
        notifications_repo.channel_out(row)
        for row in await notifications_repo.list_channels(session)
    ]


@router.post(
    "/notification-channels",
    response_model=NotificationChannelOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_channel(
    payload: NotificationChannelCreate,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("admin"))],
) -> NotificationChannelOut:
    _validate(payload)
    row = await notifications_repo.create_channel(
        session,
        name=payload.name,
        kind=payload.kind,
        url=payload.url,
        secret=payload.secret,
        chat_id=payload.chat_id,
        enabled=payload.enabled,
        created_by=principal.id,
    )
    return notifications_repo.channel_out(row)


@router.patch("/notification-channels/{channel_id}", response_model=NotificationChannelOut)
async def update_channel(
    channel_id: str,
    payload: NotificationChannelUpdate,
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_scope("admin"))],
) -> NotificationChannelOut:
    row = await notifications_repo.get_channel(session, channel_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="channel not found")
    row = await notifications_repo.update_channel(
        session, row, **payload.model_dump(exclude_unset=True)
    )
    return notifications_repo.channel_out(row)


@router.delete(
    "/notification-channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_channel(
    channel_id: str,
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_scope("admin"))],
) -> None:
    row = await notifications_repo.get_channel(session, channel_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="channel not found")
    await session.delete(row)
    await session.commit()


@router.get("/deliveries", response_model=DeliveryList)
async def list_deliveries(
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_scope("admin"))],
    limit: int = Query(default=50, ge=1, le=200),
) -> DeliveryList:
    rows = await notifications_repo.list_deliveries(session, limit=limit)
    return DeliveryList(
        items=[notifications_repo.delivery_out(row) for row in rows],
        total=len(rows),
    )
