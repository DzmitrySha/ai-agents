"""`/v1/skills`: skills.sh imports and agent-attachable skills."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.auth.deps import SessionDep, require_any_scope, require_csrf
from app.auth.principal import Principal, catalog_allowlist
from app.repos import skills as repo
from app.runtime.models import (
    SkillCreate,
    SkillDetail,
    SkillImportRequest,
    SkillList,
    SkillLocalImportRequest,
    SkillLocalImportResult,
    SkillOut,
    SkillUpdate,
)

router = APIRouter(
    prefix="/v1/skills", tags=["skills"], dependencies=[Depends(require_csrf)]
)


@router.get("", response_model=SkillList)
async def list_skills(
    session: SessionDep,
    principal: Annotated[
        Principal, Depends(require_any_scope("skills:read", "agents:read"))
    ],
    q: str | None = None,
) -> SkillList:
    rows = await repo.list_skills(session, q=q)
    allow = catalog_allowlist(principal, "skill")
    if allow is not None:
        rows = [row for row in rows if row.slug in allow]
    return SkillList(items=[repo.to_out(row) for row in rows], total=len(rows))


@router.post("", response_model=SkillDetail, status_code=status.HTTP_201_CREATED)
async def create_skill(
    payload: SkillCreate,
    session: SessionDep,
    principal: Annotated[
        Principal, Depends(require_any_scope("skills:write", "agents:write"))
    ],
) -> SkillDetail:
    """Свой навык по шаблону skills.sh (без импорта)."""
    try:
        skill = await repo.create_manual(session, data=payload, created_by=principal.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return repo.to_out(skill, detail=True)


@router.get("/search")
async def search_skills(
    _principal: Annotated[
        Principal, Depends(require_any_scope("skills:read", "agents:read"))
    ],
    q: str = Query(min_length=2),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, Any]:
    items = await repo.search_remote(q, limit)
    if items is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="skills.sh search requires SKILLS_SH_TOKEN; import by URL is available",
        )
    return {"items": items, "total": len(items)}


@router.post("/import", response_model=SkillDetail, status_code=status.HTTP_201_CREATED)
async def import_skill(
    payload: SkillImportRequest,
    session: SessionDep,
    principal: Annotated[
        Principal, Depends(require_any_scope("skills:write", "agents:write"))
    ],
) -> SkillDetail:
    try:
        skill, _created = await repo.import_skill(
            session, url=payload.url, created_by=principal.id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except Exception as exc:  # noqa: BLE001 - upstream GitHub/skills.sh errors
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"import failed: {type(exc).__name__}: {exc}",
        ) from exc
    return repo.to_out(skill, detail=True)


@router.post(
    "/import-local",
    response_model=SkillLocalImportResult,
    status_code=status.HTTP_201_CREATED,
)
async def import_skills_local(
    payload: SkillLocalImportRequest,
    session: SessionDep,
    principal: Annotated[
        Principal, Depends(require_any_scope("skills:write", "agents:write"))
    ],
) -> SkillLocalImportResult:
    """Импорт с диска backend (`path`) или загрузка файлов из браузера (`entries`)."""
    try:
        return await repo.import_from_local(
            session,
            path=payload.path,
            entries=payload.entries,
            created_by=principal.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"cannot read path: {exc}",
        ) from exc


@router.get("/{ref}", response_model=SkillDetail)
async def get_skill(
    ref: str,
    session: SessionDep,
    principal: Annotated[
        Principal, Depends(require_any_scope("skills:read", "agents:read"))
    ],
) -> SkillDetail:
    skill = await repo.get_skill(session, ref)
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="skill not found")
    allow = catalog_allowlist(principal, "skill")
    if allow is not None and skill.slug not in allow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="skill not found")
    return repo.to_out(skill, detail=True)


@router.patch("/{ref}", response_model=SkillDetail)
async def update_skill(
    ref: str,
    payload: SkillUpdate,
    session: SessionDep,
    principal: Annotated[
        Principal, Depends(require_any_scope("skills:write", "agents:write"))
    ],
) -> SkillDetail:
    skill = await repo.get_skill(session, ref)
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="skill not found")
    if not principal.is_superadmin and skill.created_by != principal.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="skill is read-only for this principal",
        )
    try:
        updated = await repo.update_manual(session, skill, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return repo.to_out(updated, detail=True)


@router.delete("/{ref}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    ref: str,
    session: SessionDep,
    principal: Annotated[
        Principal, Depends(require_any_scope("skills:write", "agents:write"))
    ],
) -> Response:
    skill = await repo.get_skill(session, ref)
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="skill not found")
    if not principal.is_superadmin and skill.created_by != principal.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="skill is read-only for this principal",
        )
    await repo.delete_skill(session, skill)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
