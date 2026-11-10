"""FastAPI auth dependencies: principal, scopes, cookie session, CSRF."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import Principal, scopes_for_role
from app.auth.service_key import authenticate_service_key, bearer_scheme, service_auth_configured
from app.db import get_session
from app.models import UserIdentity
from app.repos.auth import aware, get_session_row
from app.runtime.models import utcnow
from app.settings import Settings, get_settings

SessionDep = Annotated[AsyncSession, Depends(get_session)]
MUTATING_METHODS = frozenset({"POST", "PATCH", "DELETE", "PUT"})
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "ai-agents-ui"
DEV_ORIGINS = frozenset(
    {
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    }
)


def session_signer(settings: Settings) -> URLSafeSerializer:
    return URLSafeSerializer(settings.session_secret_key, salt=settings.session_salt)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(request: Request, session: SessionDep) -> Principal | None:
    settings = get_settings()
    raw = request.cookies.get(settings.session_cookie_name)
    if not raw:
        return None
    try:
        session_id = session_signer(settings).loads(raw)
    except BadSignature:
        return None
    row = await get_session_row(session, session_id)
    if row is None or row.revoked or aware(row.expires_at) <= utcnow():
        return None
    user = await session.get(UserIdentity, row.user_sub)
    if user is None:
        return None
    is_super = bool(user.is_superadmin or user.app_role == "superadmin")
    role = "superadmin" if is_super else (user.app_role or "user")
    request.state.principal = Principal(
        kind="user",
        id=user.sub,
        email=user.email,
        is_superadmin=is_super,
        is_bootstrap=bool(
            user.email and user.email.strip().lower() in settings.superadmin_email_set
        ),
        scopes=scopes_for_role(role),
        roles=tuple(user.roles or ()),
        app_role=role,
        daily_run_limit=user.daily_run_limit,
    )
    return request.state.principal


async def get_principal(
    request: Request,
    session: SessionDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> Principal | None:
    if credentials is not None:
        raw = credentials.credentials
        if not await service_auth_configured(session):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service authentication is not configured (SERVICE_API_KEYS is empty)",
            )
        principal = await authenticate_service_key(raw, session)
        if principal is None:
            raise _unauthorized("Invalid service key")
        request.state.principal = principal
        return principal
    if request.headers.get("authorization"):
        # Malformed / non-Bearer scheme.
        raise _unauthorized("Missing Bearer service key")
    return await get_current_user(request, session)


async def require_user(
    user: Annotated[Principal | None, Depends(get_current_user)],
) -> Principal:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


async def require_superadmin(
    user: Annotated[Principal, Depends(require_user)],
) -> Principal:
    if not user.is_superadmin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superadmin only")
    return user


async def require_principal(
    principal: Annotated[Principal | None, Depends(get_principal)],
) -> Principal:
    if principal is None:
        raise _unauthorized("Not authenticated")
    return principal


def require_scope(scope: str) -> Callable[..., Awaitable[Principal]]:
    async def _dep(
        principal: Annotated[Principal, Depends(require_principal)],
    ) -> Principal:
        if principal.is_superadmin or scope in principal.scopes:
            return principal
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing scope: {scope}"
        )

    return _dep


def require_any_scope(*scopes: str) -> Callable[..., Awaitable[Principal]]:
    needed = tuple(scopes)

    async def _dep(
        principal: Annotated[Principal, Depends(require_principal)],
    ) -> Principal:
        if principal.is_superadmin or any(scope in principal.scopes for scope in needed):
            return principal
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing scope: " + " or ".join(needed),
        )

    return _dep


async def require_csrf(
    request: Request,
    principal: Annotated[Principal | None, Depends(get_principal)],
) -> None:
    """Cookie-authenticated mutations must prove UI origin; service Bearer is exempt."""
    if request.method not in MUTATING_METHODS:
        return
    if principal is None or principal.kind == "service":
        return
    settings = get_settings()
    if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Missing CSRF header"
        )
    origin = request.headers.get("origin")
    if origin is None:
        return
    allowed = {settings.public_url.rstrip("/")}
    if settings.environment != "production":
        allowed |= DEV_ORIGINS
    if origin.rstrip("/") not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bad Origin")


def get_manager(request: Request):
    return request.app.state.run_manager
