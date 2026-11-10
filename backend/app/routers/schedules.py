"""`/v1/schedules`: cron schedules for agent runs."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth.deps import SessionDep, get_manager, require_csrf, require_scope
from app.auth.principal import Principal
from app.models import utcnow
from app.repos import schedules as schedules_repo
from app.repos.agents import resolve_agent
from app.repos.runs import DailyQuotaExceeded, DailyTokenBudgetExceeded
from app.runtime.manager import QueueFull, RunManager
from app.runtime.models import (
    CreateRunRequest,
    RunOut,
    ScheduleCreate,
    ScheduleList,
    ScheduleOut,
    ScheduleUpdate,
)
from app.runtime.scheduler import _daily_limits, principal_for_schedule

router = APIRouter(
    prefix="/v1/schedules", tags=["schedules"], dependencies=[Depends(require_csrf)]
)


def _visible(row, principal: Principal) -> bool:
    return principal.is_superadmin or (
        row.principal_kind == principal.kind and row.principal_id == principal.id
    )


async def _load(session, schedule_id: str, principal: Principal):
    row = await schedules_repo.get_schedule(session, schedule_id)
    if row is None or not _visible(row, principal):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="schedule not found")
    return row


@router.get("", response_model=ScheduleList)
async def list_schedules(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("runs:execute"))],
) -> ScheduleList:
    rows = await schedules_repo.list_schedules(session, principal)
    return ScheduleList(items=[schedules_repo.to_out(row) for row in rows], total=len(rows))


@router.post("", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    payload: ScheduleCreate,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("runs:execute"))],
) -> ScheduleOut:
    try:
        await resolve_agent(session, payload.agent_slug, principal, for_run=True)
        row = await schedules_repo.create_schedule(
            session,
            name=payload.name,
            agent_slug=payload.agent_slug,
            input_value=payload.input,
            cron=payload.cron,
            tz_name=payload.timezone,
            enabled=payload.enabled,
            p=principal,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc.args[0])
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return schedules_repo.to_out(row)


@router.get("/{schedule_id}", response_model=ScheduleOut)
async def get_schedule(
    schedule_id: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("runs:execute"))],
) -> ScheduleOut:
    return schedules_repo.to_out(await _load(session, schedule_id, principal))


@router.patch("/{schedule_id}", response_model=ScheduleOut)
async def update_schedule(
    schedule_id: str,
    payload: ScheduleUpdate,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("runs:execute"))],
) -> ScheduleOut:
    row = await _load(session, schedule_id, principal)
    fields = payload.model_dump(exclude_unset=True)
    if fields.get("agent_slug"):
        try:
            await resolve_agent(session, fields["agent_slug"], principal, for_run=True)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc.args[0])
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    try:
        row = await schedules_repo.update_schedule(
            session,
            row,
            name=fields.get("name"),
            agent_slug=fields.get("agent_slug"),
            input_value=fields.get("input"),
            cron=fields.get("cron"),
            tz_name=fields.get("timezone"),
            enabled=fields.get("enabled"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return schedules_repo.to_out(row)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("runs:execute"))],
) -> None:
    row = await _load(session, schedule_id, principal)
    await session.delete(row)
    await session.commit()


@router.post("/{schedule_id}/run-now", response_model=RunOut, status_code=status.HTTP_201_CREATED)
async def run_now(
    schedule_id: str,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("runs:execute"))],
    manager: RunManager = Depends(get_manager),
) -> RunOut:
    row = await _load(session, schedule_id, principal)
    if not row.enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="schedule is disabled")
    owner = await principal_for_schedule(session, row, request.app.state.settings)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="schedule principal is unavailable")
    run_limit, token_limit = _daily_limits(owner, request.app.state.settings)
    try:
        out = await manager.create_run(
            request.app.state.session_factory,
            owner,
            CreateRunRequest(agent_id=row.agent_slug, input=row.input),
            daily_limit=run_limit,
            daily_token_limit=token_limit,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc.args[0])
        ) from exc
    except (DailyQuotaExceeded, DailyTokenBudgetExceeded, QueueFull) as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    row.last_run_at = utcnow()
    row.last_run_id = out.run_id
    row.last_error = None
    await session.commit()
    return out
