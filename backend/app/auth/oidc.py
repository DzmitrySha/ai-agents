"""Keycloak OIDC (BFF): login redirect, callback, logout, session info."""

from __future__ import annotations

import base64
import json
from typing import Annotated
from urllib.parse import quote

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.auth.deps import SessionDep, require_user, session_signer
from app.auth.principal import Principal
from app.models import UserIdentity
from app.repos.auth import create_session, revoke_session, upsert_user
from app.settings import Settings, get_settings

router = APIRouter(prefix="/auth", tags=["auth"])
oauth = OAuth()


def register_oidc_client(settings: Settings) -> None:
    if not settings.oidc_enabled:
        return
    if "keycloak" in oauth._clients:  # registered once per process
        return
    oauth.register(
        "keycloak",
        server_metadata_url=f"{settings.keycloak_issuer}/.well-known/openid-configuration",
        client_id=settings.keycloak_client_id,
        client_secret=settings.keycloak_client_secret,
        client_kwargs={
            "scope": "openid profile email",
            "verify": settings.keycloak_ssl_context,
        },
    )


def _jwt_payload(token: str) -> dict:
    """Decode a JWT payload without verification (signature already checked by authlib)."""
    try:
        payload = token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except (IndexError, ValueError):
        return {}


def _roles(claims: dict, id_token: str, client_id: str) -> list[str]:
    sources = [claims]
    if not claims.get("realm_access") and not claims.get("resource_access"):
        sources.append(_jwt_payload(id_token))
    roles: set[str] = set()
    for source in sources:
        roles.update(source.get("realm_access", {}).get("roles", []))
        roles.update(
            source.get("resource_access", {}).get(client_id, {}).get("roles", [])
        )
    return sorted(roles)


def _safe_return_to(value: str | None) -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/agents"
    return value


@router.get("/login")
async def login(request: Request, return_to: str = "/agents") -> Response:
    settings = get_settings()
    if not settings.oidc_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC is not configured",
        )
    request.session["return_to"] = _safe_return_to(return_to)
    try:
        return await oauth.keycloak.authorize_redirect(request, settings.keycloak_redirect)
    except Exception as exc:  # noqa: BLE001 - IdP metadata/network errors
        # Не отдавать голый 500: фронт/пользователь видят причину на /login.
        return RedirectResponse(
            f"/login?error={quote(f'Keycloak недоступен: {exc}')}",
            status_code=302,
        )


@router.get("/callback")
async def callback(request: Request, session: SessionDep) -> Response:
    settings = get_settings()
    if not settings.oidc_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC is not configured",
        )
    try:
        token = await oauth.keycloak.authorize_access_token(request)
    except Exception as exc:  # noqa: BLE001 - surface IdP errors on the login page
        return RedirectResponse(f"/login?error={quote(str(exc))}", status_code=302)

    claims = dict(token.get("userinfo") or {})
    if not claims.get("sub"):
        claims = _jwt_payload(token.get("id_token") or "")
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        return RedirectResponse("/login?error=missing_sub", status_code=302)

    roles = _roles(claims, token.get("id_token") or "", settings.keycloak_client_id)
    user = await upsert_user(
        session,
        sub=sub,
        email=claims.get("email"),
        display_name=claims.get("name") or claims.get("preferred_username"),
        roles=roles,
        is_superadmin=bool(set(roles) & settings.admin_role_set),
    )
    session_row = await create_session(
        session, user_sub=user.sub, ttl_hours=settings.session_ttl_hours
    )
    return_to = _safe_return_to(request.session.pop("return_to", "/agents"))
    response = RedirectResponse(return_to, status_code=302)
    response.set_cookie(
        settings.session_cookie_name,
        session_signer(settings).dumps(session_row.id),
        httponly=True,
        samesite="lax",
        path="/",
        secure=settings.session_cookie_secure,
        max_age=settings.session_ttl_hours * 3600,
    )
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, session: SessionDep) -> Response:
    settings = get_settings()
    raw = request.cookies.get(settings.session_cookie_name)
    if raw:
        try:
            session_id = session_signer(settings).loads(raw)
        except Exception:  # noqa: BLE001 - invalid cookie is simply cleared
            session_id = None
        if session_id:
            await revoke_session(session, session_id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response


@router.get("/me")
async def me(
    user: Annotated[Principal, Depends(require_user)], session: SessionDep
) -> JSONResponse:
    row = await session.get(UserIdentity, user.id) if user.kind == "user" else None
    display_name = (row.display_name or "").strip() if row is not None else ""
    app_role = (
        "superadmin"
        if user.is_superadmin
        else ((row.app_role if row is not None else None) or user.app_role or "user")
    )
    return JSONResponse(
        {
            "authenticated": True,
            "user": {
                "id": user.id,
                "email": user.email,
                # UI показывает ФИО из Keycloak; email — только фолбэк.
                "name": display_name or user.email or user.id,
                "display_name": display_name or None,
                "is_superadmin": user.is_superadmin,
                "app_role": app_role,
                # Только bootstrap-суперадмин назначает других суперадминов.
                "can_manage_superadmins": user.is_bootstrap,
                "roles": list(user.roles),
            },
        }
    )

