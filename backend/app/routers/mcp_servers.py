"""`/api/admin/mcp-servers`: keys for the public MCP endpoint (`/mcp`)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.auth.deps import SessionDep, require_csrf, require_superadmin
from app.auth.principal import Principal
from app.models import McpServer
from app.repos import mcp_servers as repo
from app.runtime.models import (
    McpServerCreate,
    McpServerCreated,
    McpServerList,
    McpServerOut,
    McpServerUpdate,
)
from app.settings import get_settings

router = APIRouter(
    prefix="/api/admin/mcp-servers",
    tags=["mcp"],
    dependencies=[Depends(require_csrf)],
)


def _url() -> str:
    return f"{get_settings().public_url.rstrip('/')}/mcp"


def _out(row: McpServer) -> McpServerOut:
    return McpServerOut(
        id=row.id,
        slug=row.slug,
        name=row.name,
        description=row.description or "",
        enabled=row.enabled,
        agent_slugs=list(row.agent_slugs or []),
        tool_slugs=list(row.tool_slugs or []),
        skill_slugs=list(row.skill_slugs or []),
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_used_at=row.last_used_at,
        url=_url(),
    )


@router.get("", response_model=McpServerList)
async def list_servers(
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_superadmin)],
) -> McpServerList:
    rows = await repo.list_servers(session)
    return McpServerList(items=[_out(row) for row in rows], total=len(rows))


@router.post("", response_model=McpServerCreated, status_code=status.HTTP_201_CREATED)
async def create_server(
    payload: McpServerCreate,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_superadmin)],
) -> McpServerCreated:
    if await repo.get_server(session, payload.slug) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="slug already exists"
        )
    try:
        row, raw = await repo.create_server(
            session,
            created_by=principal.id,
            slug=payload.slug,
            name=payload.name,
            description=payload.description,
            agent_slugs=list(payload.agent_slugs or []),
            tool_slugs=list(payload.tool_slugs or []),
            skill_slugs=list(payload.skill_slugs or []),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return McpServerCreated(**_out(row).model_dump(), api_key=raw)


@router.patch("/{ref}", response_model=McpServerCreated | McpServerOut)
async def update_server(
    ref: str,
    payload: McpServerUpdate,
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_superadmin)],
) -> McpServerCreated | McpServerOut:
    try:
        row, raw = await repo.update_server(
            session, ref, payload, rotate_key=payload.rotate_key
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc.args[0])
        ) from exc
    except ValueError as exc:
        detail = str(exc)
        code = (
            status.HTTP_422_UNPROCESSABLE_CONTENT
            if "agent_slugs" in detail
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    out = _out(row)
    if raw is None:
        return out
    return McpServerCreated(**out.model_dump(), api_key=raw)


@router.delete("/{ref}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(
    ref: str,
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_superadmin)],
) -> Response:
    if not await repo.delete_server(session, ref):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="mcp server not found"
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
