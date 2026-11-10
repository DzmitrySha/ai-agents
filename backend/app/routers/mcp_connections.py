"""`/v1/mcp-connections`: external MCP servers used by agents' tools."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.url_safety import UnsafeUrlError
from app.auth.deps import SessionDep, require_csrf, require_scope
from app.auth.principal import Principal
from app.repos import mcp_connections as repo
from app.runtime.models import (
    McpConnectionCreate,
    McpConnectionDeleteResult,
    McpConnectionList,
    McpConnectionOut,
    McpConnectionTestResult,
    McpConnectionUpdate,
    McpToolInfo,
)

router = APIRouter(
    prefix="/v1/mcp-connections",
    tags=["mcp"],
    dependencies=[Depends(require_csrf)],
)


@router.get("", response_model=McpConnectionList)
async def list_connections(
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_scope("agents:read"))],
) -> McpConnectionList:
    rows = await repo.list_connections(session)
    return McpConnectionList(
        items=[await repo.to_out(session, row) for row in rows], total=len(rows)
    )


@router.post("", response_model=McpConnectionOut, status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: McpConnectionCreate,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("agents:write"))],
) -> McpConnectionOut:
    try:
        conn = await repo.create_connection(session, principal, payload)
    except UnsafeUrlError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return await repo.to_out(session, conn)


@router.get("/{ref}", response_model=McpConnectionOut)
async def get_connection(
    ref: str,
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_scope("agents:read"))],
) -> McpConnectionOut:
    conn = await repo.get_connection(session, ref)
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="mcp connection not found"
        )
    return await repo.to_out(session, conn)


@router.patch("/{ref}", response_model=McpConnectionOut)
async def update_connection(
    ref: str,
    payload: McpConnectionUpdate,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("agents:write"))],
) -> McpConnectionOut:
    try:
        conn = await repo.update_connection(session, principal, ref, payload)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc.args[0])
        ) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except (UnsafeUrlError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return await repo.to_out(session, conn)


@router.delete("/{ref}", response_model=McpConnectionDeleteResult)
async def delete_connection(
    ref: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("agents:write"))],
) -> McpConnectionDeleteResult:
    try:
        detached = await repo.delete_connection(session, principal, ref)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc.args[0])
        ) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return McpConnectionDeleteResult(slug=ref, detached_agents=detached)


@router.post("/{ref}/test", response_model=McpConnectionTestResult)
async def test_connection(
    ref: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("agents:write"))],
) -> McpConnectionTestResult:
    conn = await repo.get_connection(session, ref)
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="mcp connection not found"
        )
    if not repo.can_edit(conn, principal):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="mcp connection is read-only for this principal",
        )
    tools, error = await repo.probe(session, conn)
    return McpConnectionTestResult(
        ok=error is None,
        tools=[McpToolInfo(**tool) for tool in tools],
        error=error,
    )
