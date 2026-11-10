"""Keycloak (Keycloak) admin API: read-only user directory.

Uses the confidential client's service account (client_credentials): the client
must have the realm-management role `view-users`. Nothing is cached on disk; the
access token is kept in memory until it expires.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.settings import get_settings

TOKEN_TIMEOUT_SECONDS = 10.0
_TOKEN_SKEW_SECONDS = 30

_cache: dict[str, Any] = {"key": None, "token": None, "expires_at": 0.0}


class DirectoryError(RuntimeError):
    """Keycloak is unreachable or the client may not read users (router → 502)."""


def _issuer() -> str:
    return get_settings().keycloak_issuer.rstrip("/")


def _admin_base() -> str:
    """https://id.example/realms/ai-agents → https://id.example"""
    return _issuer().split("/realms/", 1)[0]


def _admin_credentials() -> tuple[str, str]:
    """Клиент каталога: DIRECTORY_ADMIN_CLIENT_* если задан, иначе основной OIDC-клиент."""
    settings = get_settings()
    if settings.keycloak_admin_client_id:
        return settings.keycloak_admin_client_id, settings.keycloak_admin_client_secret
    return settings.keycloak_client_id, settings.keycloak_client_secret


async def _service_token() -> str:
    settings = get_settings()
    if not settings.oidc_enabled:
        raise DirectoryError("не сконфигурирован: нет KEYCLOAK_CLIENT_ID/SECRET")
    client_id, client_secret = _admin_credentials()
    if not client_id or not client_secret:
        raise DirectoryError("не сконфигурирован клиент Keycloak (DIRECTORY_ADMIN_CLIENT_ID/SECRET)")
    key = (_issuer(), client_id, settings.keycloak_realm)
    now = time.monotonic()
    if _cache["token"] and _cache["key"] == key and _cache["expires_at"] > now:
        return str(_cache["token"])

    try:
        async with httpx.AsyncClient(
            verify=settings.keycloak_ssl_context, timeout=TOKEN_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(
                f"{_issuer()}/protocol/openid-connect/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
    except httpx.HTTPError as exc:
        raise DirectoryError(f"{type(exc).__name__}: {exc}") from exc
    if response.status_code >= 400:
        raise DirectoryError(
            f"token endpoint HTTP {response.status_code}: {response.text.strip()[:200]}"
        )
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise DirectoryError("ответ без access_token")
    _cache.update(
        key=key,
        token=token,
        expires_at=now + max(30, int(payload.get("expires_in") or 60) - _TOKEN_SKEW_SECONDS),
    )
    return str(token)


def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    first = str(item.get("firstName") or "").strip()
    last = str(item.get("lastName") or "").strip()
    username = str(item.get("username") or "").strip()
    return {
        "sub": str(item.get("id") or ""),
        "username": username,
        "email": (str(item.get("email") or "").strip() or None),
        "display_name": " ".join(part for part in (first, last) if part) or username or None,
        "enabled": bool(item.get("enabled", True)),
    }


async def search_users(
    query: str = "", limit: int = 20, first: int = 0
) -> dict[str, Any]:
    settings = get_settings()
    token = await _service_token()
    size = max(1, min(limit, 50))
    params: dict[str, str] = {
        "max": str(size),
        "first": str(max(0, first)),
        "briefRepresentation": "true",
    }
    if query.strip():
        params["search"] = query.strip()
    url = f"{_admin_base()}/admin/realms/{settings.keycloak_realm}/users"
    try:
        async with httpx.AsyncClient(
            verify=settings.keycloak_ssl_context, timeout=TOKEN_TIMEOUT_SECONDS
        ) as client:
            response = await client.get(
                url, params=params, headers={"Authorization": f"Bearer {token}"}
            )
    except httpx.HTTPError as exc:
        raise DirectoryError(f"{type(exc).__name__}: {exc}") from exc

    if response.status_code == 401:
        raise DirectoryError("Keycloak отклонил токен сервисного аккаунта (401)")
    if response.status_code == 403:
        raise DirectoryError(
            "клиенту не выдано право чтения пользователей realm-management: view-users (403)"
        )
    if response.status_code >= 400:
        raise DirectoryError(f"HTTP {response.status_code}: {response.text.strip()[:200]}")

    try:
        items = response.json()
    except ValueError as exc:
        raise DirectoryError("ответ Keycloak не JSON") from exc
    if not isinstance(items, list):
        raise DirectoryError("ответ Keycloak не список пользователей")
    page = [
        _normalize(item)
        for item in items
        if isinstance(item, dict) and item.get("id")
    ]
    return {"items": page, "has_more": len(items) >= size}
