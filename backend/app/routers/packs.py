"""`/v1/packs`: code-registered bundles of agents + existing refs."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError

from app.auth.deps import SessionDep, require_csrf, require_superadmin
from app.auth.principal import Principal
from app.plugins import packs as registry
from app.repos import packs as repo
from app.runtime.models import PackInstallResult, PackManifest, PackOut

router = APIRouter(
    prefix="/v1/packs", tags=["packs"], dependencies=[Depends(require_csrf)]
)


@router.get("", response_model=list[PackOut])
async def list_packs(
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_superadmin)],
) -> list[PackOut]:
    items = [
        await repo.to_out(session, item)
        for item in registry.list_packs()
    ]
    items.extend(
        [
            await repo.to_out(session, item, source="custom")
            for item in await repo.list_custom(session)
        ]
    )
    return sorted(items, key=lambda item: item.name)


@router.post("", response_model=PackOut, status_code=status.HTTP_201_CREATED)
async def create_pack(
    manifest: PackManifest,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_superadmin)],
) -> PackOut:
    if manifest.name in registry.PACKS or await repo.get_custom(
        session, manifest.name
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"pack already exists: {manifest.name}",
        )
    try:
        await repo.create_custom(session, principal, manifest)
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"pack already exists: {manifest.name}",
        ) from exc
    return await repo.to_out(session, manifest, source="custom")


@router.put("/{name}", response_model=PackOut)
async def update_pack(
    name: str,
    manifest: PackManifest,
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_superadmin)],
) -> PackOut:
    if manifest.name != name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="manifest name must match path",
        )
    if not await repo.update_custom(session, name, manifest):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"custom pack not found: {name}",
        )
    return await repo.to_out(session, manifest, source="custom")


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pack(
    name: str,
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_superadmin)],
) -> None:
    if name in registry.PACKS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="code-registered packs are immutable",
        )
    if not await repo.delete_custom(session, name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"custom pack not found: {name}",
        )


@router.post("/{name}/install", response_model=PackInstallResult)
async def install_pack(
    name: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_superadmin)],
    dry_run: bool = Query(default=False),
) -> PackInstallResult:
    try:
        manifest = await repo.get_custom(session, name) or registry.get_pack(name)
    except registry.PackNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"pack not found: {name}"
        ) from exc
    try:
        return await repo.install(
            session, principal, manifest, dry_run=dry_run
        )
    except repo.PackValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except repo.PackConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
