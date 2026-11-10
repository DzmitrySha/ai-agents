"""Agent memory read/delete API for the editor."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.deps import SessionDep, require_csrf, require_scope
from app.auth.principal import Principal
from app.repos import memory as memory_repo
from app.repos.agents import resolve_editable
from app.runtime.models import AgentMemoryOut

router = APIRouter(
    prefix="/v1/agents", tags=["memory"], dependencies=[Depends(require_csrf)]
)


@router.get("/{ref}/memories", response_model=list[AgentMemoryOut])
async def list_memories(
    ref: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("agents:read"))],
) -> list[AgentMemoryOut]:
    agent = await resolve_editable(session, ref, principal)
    rows = await memory_repo.list_for_agent(
        session,
        agent.id,
        principal_kind=None if principal.is_superadmin else principal.kind,
        principal_id=None if principal.is_superadmin else principal.id,
    )
    return [memory_repo.to_out(row) for row in rows]


@router.delete("/{ref}/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    ref: str,
    memory_id: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("agents:write"))],
) -> None:
    agent = await resolve_editable(session, ref, principal)
    if not await memory_repo.delete_entry(session, agent.id, memory_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="memory not found")
