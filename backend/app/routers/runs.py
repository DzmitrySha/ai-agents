"""`/v1/runs`: create, status/list, SSE events with replay, cancel."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from app.auth.deps import SessionDep, get_manager, require_csrf, require_scope
from app.auth.principal import Principal
from app.repos import approvals as approvals_repo
from app.repos.runs import (
    DailyQuotaExceeded,
    DailyTokenBudgetExceeded,
    IdempotencyConflict,
    _version_number,
    can_view_run,
    get_agent_for_run,
    get_run_by_idempotency,
    get_run_row,
    list_run_rows,
    load_run_events,
    to_out,
)
from app.runtime.digest import build_digest
from app.runtime.harness import diff_harness
from app.runtime.manager import QueueFull, RunManager
from app.runtime.preflight import run_preflight
from app.settings import get_settings
from app.runtime.models import (
    TERMINAL_STATUSES,
    ApprovalDecision,
    CreateRunRequest,
    PreflightRequest,
    PreflightResult,
    RunApprovalOut,
    RunCompareResult,
    RunEvent,
    RunHarness,
    RunList,
    RunOut,
    RunStatus,
    TrajectoryDigest,
)

router = APIRouter(
    prefix="/v1/runs", tags=["runs"], dependencies=[Depends(require_csrf)]
)

TERMINAL_EVENTS = frozenset({"run.completed", "run.failed", "run.cancelled"})


def _sse(seq: int, event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"id: {seq}\nevent: {event}\ndata: {payload}\n\n"


@router.post("", response_model=RunOut, status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: CreateRunRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("runs:execute"))],
    manager: RunManager = Depends(get_manager),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        max_length=128,
    ),
) -> RunOut:
    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip() or None
    if idempotency_key and not re.fullmatch(r"[A-Za-z0-9_.:-]+", idempotency_key):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Idempotency-Key must match ^[A-Za-z0-9_.:-]{1,128}$",
        )
    if idempotency_key:
        existing = await get_run_by_idempotency(
            session,
            principal_kind=principal.kind,
            principal_id=principal.id,
            key=idempotency_key,
        )
        if existing is not None:
            response.status_code = status.HTTP_200_OK
            return await to_out(session, existing)
    try:
        return await manager.create_run(
            request.app.state.session_factory,
            principal,
            payload,
            daily_limit=_daily_limit(principal),
            daily_token_limit=_daily_token_limit(principal),
            idempotency_key=idempotency_key,
        )
    except IdempotencyConflict as exc:
        row = await get_run_row(session, exc.run_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="idempotency conflict"
            ) from exc
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotency-Replayed"] = "true"
        return await to_out(session, row)
    except (DailyQuotaExceeded, DailyTokenBudgetExceeded, QueueFull) as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc.args[0])
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _daily_limit(principal: Principal) -> int | None:
    """Quota applies to role=user only; 0/None means unlimited."""
    if principal.is_superadmin or principal.app_role != "user":
        return None
    limit = principal.daily_run_limit
    if limit is None:
        limit = get_settings().user_daily_run_limit
    return limit or None


def _daily_token_limit(principal: Principal) -> int | None:
    """Daily token budget applies to role=user only; 0 means unlimited."""
    if principal.is_superadmin or principal.app_role != "user":
        return None
    return get_settings().user_daily_token_limit or None


@router.post("/preflight", response_model=PreflightResult)
async def preflight_run(
    payload: PreflightRequest,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("runs:execute"))],
) -> PreflightResult:
    try:
        return await run_preflight(session, principal, payload)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc.args[0])
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.get("/compare", response_model=RunCompareResult)
async def compare_runs(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("runs:read"))],
    left: str = Query(min_length=1),
    right: str = Query(min_length=1),
) -> RunCompareResult:
    if left == right:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="left and right must differ",
        )

    async def load_visible(run_id: str):
        row = await get_run_row(session, run_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="run not found"
            )
        agent = await get_agent_for_run(session, row)
        if not can_view_run(row, agent, principal):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="run not found"
            )
        return row

    async def digest_out(row) -> TrajectoryDigest:
        if row.digest is not None:
            data = dict(row.digest)
        else:
            events = await load_run_events(session, row.id)
            data = build_digest(row, events)
        data["agent_version"] = await _version_number(session, row.agent_version_id)
        return TrajectoryDigest(**data)

    left_row = await load_visible(left)
    right_row = await load_visible(right)
    left_digest = await digest_out(left_row)
    right_digest = await digest_out(right_row)
    left_out = await to_out(session, left_row)
    right_out = await to_out(session, right_row)
    return RunCompareResult(
        left=left_out,
        right=right_out,
        left_digest=left_digest,
        right_digest=right_digest,
        diff=diff_harness(
            left_out,
            right_out,
            left_row.harness_snapshot,
            right_row.harness_snapshot,
            left_digest,
            right_digest,
        ),
    )


@router.get("", response_model=RunList)
async def list_runs(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("runs:read"))],
    status_filter: str | None = Query(default=None, alias="status"),
    agent_id: str | None = None,
    parent_run_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RunList:
    rows, total = await list_run_rows(
        session,
        principal,
        status=status_filter,
        agent_id=agent_id,
        limit=limit,
        offset=offset,
        parent_run_id=parent_run_id,
    )
    return RunList(items=[await to_out(session, row) for row in rows], total=total)


@router.get("/{run_id}", response_model=RunOut)
async def get_run(
    run_id: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("runs:read"))],
) -> RunOut:
    row = await get_run_row(session, run_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    agent = await get_agent_for_run(session, row)
    if not can_view_run(row, agent, principal):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    return await to_out(session, row)


@router.get("/{run_id}/harness", response_model=RunHarness)
async def get_run_harness(
    run_id: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("runs:read"))],
) -> RunHarness:
    row = await get_run_row(session, run_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    agent = await get_agent_for_run(session, row)
    if not can_view_run(row, agent, principal):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    return RunHarness(
        run_id=row.id,
        harness_hash=row.harness_hash,
        snapshot=row.harness_snapshot,
    )


@router.get("/{run_id}/digest", response_model=TrajectoryDigest)
async def get_run_digest(
    run_id: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("runs:read"))],
) -> TrajectoryDigest:
    row = await get_run_row(session, run_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    agent = await get_agent_for_run(session, row)
    if not can_view_run(row, agent, principal):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    if row.digest is not None:
        data = dict(row.digest)
    else:
        events = await load_run_events(session, run_id)
        data = build_digest(row, events)
    data["agent_version"] = await _version_number(session, row.agent_version_id)
    return TrajectoryDigest(**data)


@router.get("/{run_id}/transcript")
async def get_run_transcript(
    run_id: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("runs:read"))],
) -> dict[str, Any]:
    row = await get_run_row(session, run_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    agent = await get_agent_for_run(session, row)
    if not can_view_run(row, agent, principal):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    if row.events_archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="transcript archived"
        )
    events = await load_run_events(session, run_id)
    if row.digest is not None:
        digest_data = dict(row.digest)
    else:
        digest_data = build_digest(row, events)
    digest_data["agent_version"] = await _version_number(
        session, row.agent_version_id
    )
    return {
        "run": await to_out(session, row),
        "digest": TrajectoryDigest(**digest_data),
        "events": [
            {
                "seq": item.seq,
                "event": item.event,
                "data": dict(item.data or {}),
                "created_at": item.created_at,
            }
            for item in events
        ],
    }


def _approval_out(row) -> RunApprovalOut:
    return RunApprovalOut(
        id=row.id,
        run_id=row.run_id,
        tool=row.tool,
        input=dict(row.input or {}),
        status=row.status,
        requested_at=row.requested_at,
        resolved_at=row.resolved_at,
        resolved_by=row.resolved_by,
    )


@router.get("/{run_id}/approvals", response_model=list[RunApprovalOut])
async def list_approvals(
    run_id: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("runs:read"))],
) -> list[RunApprovalOut]:
    row = await get_run_row(session, run_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    agent = await get_agent_for_run(session, row)
    if not can_view_run(row, agent, principal):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    return [_approval_out(item) for item in await approvals_repo.list_approvals(
        session, run_id
    )]


@router.post(
    "/{run_id}/approvals/{approval_id}", response_model=RunApprovalOut
)
async def decide_approval(
    run_id: str,
    approval_id: str,
    payload: ApprovalDecision,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("runs:execute"))],
    manager: RunManager = Depends(get_manager),
) -> RunApprovalOut:
    row = await get_run_row(session, run_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    agent = await get_agent_for_run(session, row)
    if not can_view_run(row, agent, principal):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    if not (
        principal.is_superadmin
        or (row.principal_kind == principal.kind and row.principal_id == principal.id)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not run owner")
    approval = await approvals_repo.get_approval(session, approval_id)
    if approval is None or approval.run_id != run_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="approval not found"
        )
    if approval.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"approval already {approval.status}",
        )
    resolved = await manager.resolve_approval(
        request.app.state.session_factory,
        run_id,
        approval_id,
        approved=payload.decision == "approve",
        resolved_by=principal.id,
    )
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="approval is not pending"
        )
    return _approval_out(resolved)


@router.post("/{run_id}/cancel", response_model=RunOut)
async def cancel_run(
    run_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("runs:execute"))],
    manager: RunManager = Depends(get_manager),
) -> RunOut:
    run = await manager.cancel_run(
        request.app.state.session_factory, run_id, principal
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    return run


@router.get("/{run_id}/events")
async def stream_events(
    run_id: str,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("runs:read"))],
    manager: RunManager = Depends(get_manager),
    after: int = Query(default=0, ge=0),
) -> StreamingResponse:
    row = await get_run_row(session, run_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    agent = await get_agent_for_run(session, row)
    if not can_view_run(row, agent, principal):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")

    if row.events_archived_at is not None:
        if row.status == RunStatus.succeeded.value:
            event_name = "run.completed"
            event_data: dict[str, Any] = {"output": row.output}
        elif row.status == RunStatus.failed.value:
            event_name = "run.failed"
            event_data = {"error": row.error}
        else:
            event_name = "run.cancelled"
            event_data = {}

        async def archived_stream() -> AsyncIterator[str]:
            if after < 1:
                yield _sse(1, event_name, event_data)

        return StreamingResponse(
            archived_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    session_factory = request.app.state.session_factory
    queue = await manager.hub.subscribe(run_id)

    async def event_stream() -> AsyncIterator[str]:
        last_seq = after
        try:
            async with session_factory() as db:
                history = await load_run_events(db, run_id, after_seq=after)
            for item in history:
                last_seq = item.seq
                yield _sse(item.seq, item.event, dict(item.data or {}))
                if item.event in TERMINAL_EVENTS:
                    return
            async with session_factory() as db:
                current = await get_run_row(db, run_id)
            if current is None or current.status in TERMINAL_STATUSES:
                return
            while True:
                event = await queue.get()
                if event is None:
                    break
                assert isinstance(event, RunEvent)
                if event.seq <= last_seq:
                    continue
                last_seq = event.seq
                yield _sse(event.seq, event.event, event.data)
                if event.event in TERMINAL_EVENTS:
                    break
        except asyncio.CancelledError:
            raise
        finally:
            await manager.hub.unsubscribe(run_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
