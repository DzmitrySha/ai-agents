"""`/v1/tools`: builtin registry + no-code custom HTTP tools."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.agents.url_safety import UnsafeUrlError
from app.auth.deps import SessionDep, require_any_scope, require_csrf, require_scope
from app.auth.principal import Principal, catalog_allowlist
from app.repos import tools as repo
from app.runtime.models import (
    ToolCreate,
    ToolDeleteResult,
    ToolInvokeRequest,
    ToolInvokeResult,
    ToolList,
    ToolOut,
    ToolSpec,
    ToolTestRequest,
    ToolTestResult,
    ToolUpdate,
    ToolUsageOut,
)

router = APIRouter(
    prefix="/v1/tools", tags=["tools"], dependencies=[Depends(require_csrf)]
)


@router.get("", response_model=list[ToolSpec])
async def list_tools(
    session: SessionDep,
    _principal: Annotated[
        Principal, Depends(require_any_scope("tools:read", "agents:read"))
    ],
) -> list[ToolSpec]:
    return [ToolSpec(**spec) for spec in await repo.tool_specs(session)]


@router.get("/custom", response_model=ToolList)
async def list_custom_tools(
    session: SessionDep,
    _principal: Annotated[
        Principal, Depends(require_any_scope("tools:read", "agents:read"))
    ],
    q: str | None = None,
    include_disabled: bool = Query(default=True),
) -> ToolList:
    rows = await repo.list_tools(session, q=q, include_disabled=include_disabled)
    return ToolList(
        items=[await repo.to_out(session, row) for row in rows], total=len(rows)
    )


@router.post("", response_model=ToolOut, status_code=status.HTTP_201_CREATED)
async def create_tool(
    payload: ToolCreate,
    session: SessionDep,
    principal: Annotated[
        Principal, Depends(require_any_scope("tools:write", "agents:write"))
    ],
) -> ToolOut:
    try:
        tool = await repo.create_tool(session, principal, payload)
    except UnsafeUrlError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return await repo.to_out(session, tool)


@router.get("/{ref}", response_model=ToolOut)
async def get_tool(
    ref: str,
    session: SessionDep,
    _principal: Annotated[
        Principal, Depends(require_any_scope("tools:read", "agents:read"))
    ],
) -> ToolOut:
    tool = await repo.get_tool(session, ref)
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tool not found")
    return await repo.to_out(session, tool)


@router.get("/{ref}/usage", response_model=ToolUsageOut)
async def tool_usage(
    ref: str,
    session: SessionDep,
    _principal: Annotated[
        Principal, Depends(require_any_scope("tools:read", "agents:read"))
    ],
) -> ToolUsageOut:
    usage = await repo.tool_usage(session, ref)
    if usage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tool not found")
    return usage


@router.patch("/{ref}", response_model=ToolOut)
async def update_tool(
    ref: str,
    payload: ToolUpdate,
    session: SessionDep,
    principal: Annotated[
        Principal, Depends(require_any_scope("tools:write", "agents:write"))
    ],
) -> ToolOut:
    try:
        tool = await repo.update_tool(session, principal, ref, payload)
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
    return await repo.to_out(session, tool)


@router.delete("/{ref}", response_model=ToolDeleteResult)
async def delete_tool(
    ref: str,
    session: SessionDep,
    principal: Annotated[
        Principal, Depends(require_any_scope("tools:write", "agents:write"))
    ],
) -> ToolDeleteResult:
    """Delete the tool and detach it from every agent that referenced it."""
    try:
        detached = await repo.delete_tool(session, principal, ref)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc.args[0])
        ) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return ToolDeleteResult(slug=ref, detached_agents=detached)


@router.post("/{ref}/test", response_model=ToolTestResult)
async def test_tool(
    ref: str,
    payload: ToolTestRequest,
    session: SessionDep,
    _principal: Annotated[
        Principal, Depends(require_any_scope("tools:write", "agents:write"))
    ],
) -> ToolTestResult:
    tool = await repo.get_tool(session, ref)
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tool not found")
    return await repo.test_tool(tool, payload.params)


@router.post("/{ref}/invoke", response_model=ToolInvokeResult)
async def invoke_tool(
    ref: str,
    payload: ToolInvokeRequest,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("tools:execute"))],
) -> ToolInvokeResult:
    """Execute a tool without an agent run (factory / external orchestrators)."""
    allow = catalog_allowlist(principal, "tool")
    if allow is not None and ref not in allow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tool not found")
    try:
        result = await repo.invoke_by_name(session, ref, payload.params)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="tool not found"
        ) from None
    return ToolInvokeResult(ok=result.ok, output=result.output)
