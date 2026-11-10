"""`/api/admin`: users and service keys (cookie superadmin only)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import directory
from app.auth.deps import SessionDep, require_csrf, require_superadmin
from app.auth.principal import Principal
from app.models import ServiceKey, UserIdentity, utcnow
from app.repos import auth as auth_repo
from app.repos import runs as runs_repo
from app.repos import service_keys as keys_repo
from app.settings import get_settings
from app.runtime.models import (
    AdminUserCreate,
    AdminUserOut,
    AdminUserUpdate,
    IdentityUser,
    IdentityUserPage,
    ServiceKeyCreate,
    ServiceKeyCreated,
    ServiceKeyOut,
    ServiceKeyUpdate,
)

router = APIRouter(
    prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_csrf)]
)


async def _user_json(session, user: UserIdentity) -> AdminUserOut:
    since = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    runs_today = await runs_repo.count_runs_since(
        session, principal_kind="user", principal_id=user.sub, since=since
    )
    is_super = bool(user.is_superadmin or user.app_role == "superadmin")
    return AdminUserOut(
        id=user.sub,
        email=user.email,
        display_name=user.display_name,
        is_superadmin=is_super,
        is_bootstrap=bool(
            user.email and user.email.strip().lower() in get_settings().superadmin_email_set
        ),
        roles=list(user.roles or []),
        app_role="superadmin" if is_super else (user.app_role or "user"),
        daily_run_limit=user.daily_run_limit,
        runs_today=runs_today,
        last_login_at=user.last_login_at,
    )


def _key_json(key: ServiceKey) -> ServiceKeyOut:
    return ServiceKeyOut(
        id=key.id,
        name=key.name,
        scopes=list(key.scopes or []),
        agent_slugs=list(key.agent_slugs or []),
        tool_slugs=list(key.tool_slugs or []),
        skill_slugs=list(key.skill_slugs or []),
        enabled=key.enabled,
        created_at=key.created_at,
        last_used_at=key.last_used_at,
    )


BOOTSTRAP_ONLY_DETAIL = (
    "назначать и снимать суперадминов может только bootstrap-суперадмин "
    "(SUPERADMIN_EMAILS)"
)


def _forbid_superadmin_management() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail=BOOTSTRAP_ONLY_DETAIL
    )


def _guard_superadmin_create(principal: Principal, app_role: str) -> None:
    if app_role == "superadmin" and not principal.is_bootstrap:
        raise _forbid_superadmin_management()


def _guard_superadmin_update(
    principal: Principal, target: UserIdentity, app_role: str | None
) -> None:
    """Только bootstrap-суперадмин назначает/снимает суперадминов.

    Демоция bootstrap-аккаунта запрещена всем: SUPERADMIN_EMAILS возвращаются в
    суперадмины при старте и при логине, поэтому такая правка всё равно откатится.
    """
    if app_role is None:
        return
    if (
        target.email
        and target.email.strip().lower() in get_settings().superadmin_email_set
        and app_role != "superadmin"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="bootstrap-суперадмина нельзя понизить (SUPERADMIN_EMAILS)",
        )
    changes_superadmin = (app_role == "superadmin") != bool(target.is_superadmin)
    if changes_superadmin and not principal.is_bootstrap:
        raise _forbid_superadmin_management()


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_superadmin)],
) -> list[AdminUserOut]:
    users = await auth_repo.list_users(session)
    return [await _user_json(session, user) for user in users]


@router.get("/identity-users", response_model=IdentityUserPage)
async def list_identity_users(
    _principal: Annotated[Principal, Depends(require_superadmin)],
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    first: int = Query(default=0, ge=0),
) -> IdentityUserPage:
    """Каталог Keycloak: пользователя выбирают из списка, а не вписывают sub руками."""
    try:
        page = await directory.search_users(q, limit, first)
    except directory.DirectoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Keycloak: {exc}"
        ) from exc
    return IdentityUserPage(
        items=[IdentityUser(**item) for item in page["items"]],
        has_more=bool(page["has_more"]),
    )


@router.post("/users", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: AdminUserCreate,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_superadmin)],
) -> AdminUserOut:
    if await auth_repo.get_user(session, payload.sub) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="user already exists"
        )
    _guard_superadmin_create(principal, payload.app_role)
    user = await auth_repo.create_user(
        session,
        sub=payload.sub,
        email=payload.email,
        display_name=payload.display_name,
        app_role=payload.app_role,
        daily_run_limit=payload.daily_run_limit,
    )
    return await _user_json(session, user)


@router.patch("/users/{sub}", response_model=AdminUserOut)
async def update_user(
    sub: str,
    payload: AdminUserUpdate,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_superadmin)],
) -> AdminUserOut:
    provided = payload.model_dump(exclude_unset=True)
    target = await auth_repo.get_user(session, sub)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    _guard_superadmin_update(principal, target, provided.get("app_role"))
    user = await auth_repo.update_user(
        session,
        sub,
        app_role=provided.get("app_role"),
        daily_run_limit=provided.get("daily_run_limit"),
        set_daily_run_limit="daily_run_limit" in provided,
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return await _user_json(session, user)


@router.get("/service-keys", response_model=list[ServiceKeyOut])
async def list_service_keys(
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_superadmin)],
) -> list[ServiceKeyOut]:
    return [_key_json(key) for key in await keys_repo.list_keys(session)]


@router.post(
    "/service-keys", response_model=ServiceKeyCreated, status_code=status.HTTP_201_CREATED
)
async def create_service_key(
    payload: ServiceKeyCreate,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_superadmin)],
) -> ServiceKeyCreated:
    try:
        key, raw = await keys_repo.create_key(
            session,
            created_by=principal.id,
            name=payload.name,
            scopes=payload.scopes,
            agent_slugs=list(payload.agent_slugs or []),
            tool_slugs=list(payload.tool_slugs or []),
            skill_slugs=list(payload.skill_slugs or []),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return ServiceKeyCreated(**_key_json(key).model_dump(), key=raw)


@router.patch("/service-keys/{key_id}", response_model=ServiceKeyOut)
async def update_service_key(
    key_id: str,
    payload: ServiceKeyUpdate,
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_superadmin)],
) -> ServiceKeyOut:
    try:
        key = await keys_repo.update_key(session, key_id, payload)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc.args[0])
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return _key_json(key)


@router.post("/service-keys/{key_id}/revoke", response_model=ServiceKeyOut)
async def revoke_service_key(
    key_id: str,
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_superadmin)],
) -> ServiceKeyOut:
    key = await keys_repo.revoke_key(session, key_id)
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="service key not found"
        )
    return _key_json(key)


@router.delete("/service-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_key(
    key_id: str,
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_superadmin)],
) -> None:
    deleted = await keys_repo.delete_key(session, key_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="service key not found"
        )
