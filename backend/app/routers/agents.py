"""`/v1/agents`: CRUD, publish, clone, versions."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.auth.deps import SessionDep, require_csrf, require_scope
from app.auth.principal import Principal
from app.repos import agents as repo
from app.repos.errors import UnknownRefs
from app.runtime.models import (
    RollbackRequest,
    AgentList,
    AgentOut,
    AgentUpdate,
    AgentUpsert,
    AgentVersionInfo,
    PublishRequest,
)

router = APIRouter(
    prefix="/v1/agents", tags=["agents"], dependencies=[Depends(require_csrf)]
)


def _not_found(exc: KeyError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc.args[0]))


def _read_only(exc: PermissionError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.get("", response_model=AgentList)
async def list_agents_endpoint(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("agents:read"))],
    scope: str | None = Query(default=None, pattern="^(owned|shared|all|archived)$"),
    stale: str | None = Query(default=None, pattern="^(skills|tools|any)$"),
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AgentList:
    effective = scope or ("owned" if principal.kind == "user" else "shared")
    if effective == "all" and not principal.is_superadmin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superadmin only")
    rows, total, precomputed = await repo.list_agents(
        session,
        principal,
        scope=effective,
        q=q,
        limit=limit,
        offset=offset,
        stale=stale,
    )
    if precomputed is not None:
        return AgentList(items=precomputed, total=total)
    return AgentList(items=await repo.to_out_many(session, rows), total=total)


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent_endpoint(
    payload: AgentUpsert,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("agents:write"))],
) -> AgentOut:
    try:
        agent = await repo.create_agent(session, principal, payload)
    except PermissionError as exc:
        raise _read_only(exc) from exc
    except UnknownRefs as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return await repo.to_out(session, agent)


@router.get("/{ref}", response_model=AgentOut)
async def get_agent_endpoint(
    ref: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("agents:read"))],
) -> AgentOut:
    try:
        agent = await repo.resolve_agent(session, ref, principal, for_run=False)
    except KeyError as exc:
        raise _not_found(exc) from exc
    return await repo.to_out(session, agent)


@router.patch("/{ref}", response_model=AgentOut)
async def update_agent_endpoint(
    ref: str,
    payload: AgentUpdate,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("agents:write"))],
) -> AgentOut:
    try:
        agent = await repo.update_agent(session, principal, ref, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except PermissionError as exc:
        raise _read_only(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return await repo.to_out(session, agent)


@router.delete(
    "/{ref}",
    response_model=None,
    responses={
        200: {"model": AgentOut, "description": "Агент переведён в архив"},
        204: {"description": "Архивный агент удалён безвозвратно"},
    },
)
async def delete_agent_endpoint(
    ref: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("agents:write"))],
) -> AgentOut | Response:
    """Первый DELETE — архив; повторный DELETE по уже архивному — полное удаление."""
    try:
        agent = await repo.resolve_editable(session, ref, principal)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except PermissionError as exc:
        raise _read_only(exc) from exc

    if agent.status == "archived":
        try:
            await repo.purge_agent(session, principal, ref)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    archived = await repo.archive_agent(session, principal, ref)
    return await repo.to_out(session, archived)


@router.post("/{ref}/publish", response_model=AgentOut)
async def publish_agent_endpoint(
    ref: str,
    payload: PublishRequest,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("agents:write"))],
) -> AgentOut:
    try:
        agent, _version = await repo.publish_agent(
            session, principal, ref, payload.visibility
        )
    except KeyError as exc:
        raise _not_found(exc) from exc
    except PermissionError as exc:
        raise _read_only(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return await repo.to_out(session, agent)


@router.post("/{ref}/rollback", response_model=AgentOut)
async def rollback_agent_endpoint(
    ref: str,
    payload: RollbackRequest,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("agents:write"))],
) -> AgentOut:
    """Вернуть агента к снимку указанной версии (публикуется новая версия)."""
    try:
        agent, _version = await repo.rollback_agent(
            session, principal, ref, payload.version, payload.visibility
        )
    except KeyError as exc:
        raise _not_found(exc) from exc
    except PermissionError as exc:
        raise _read_only(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return await repo.to_out(session, agent)


@router.post("/{ref}/clone", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def clone_agent_endpoint(
    ref: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("agents:write"))],
) -> AgentOut:
    try:
        agent = await repo.clone_agent(session, principal, ref)
    except KeyError as exc:
        raise _not_found(exc) from exc
    return await repo.to_out(session, agent)


@router.get("/{ref}/versions", response_model=list[AgentVersionInfo])
async def list_versions_endpoint(
    ref: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("agents:read"))],
) -> list[AgentVersionInfo]:
    try:
        versions = await repo.list_versions(session, principal, ref)
    except KeyError as exc:
        raise _not_found(exc) from exc
    return [
        AgentVersionInfo(
            id=version.id,
            version=version.version,
            created_by=version.created_by,
            created_at=version.created_at,
            snapshot=dict(version.snapshot or {}),
        )
        for version in versions
    ]
