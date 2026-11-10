"""Service-key Bearer authentication (env bootstrap keys or DB keys)."""

from __future__ import annotations

import secrets

from fastapi.security import HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import Principal, service_all_scopes
from app.models import ServiceKey
from app.repos.service_keys import authenticate as authenticate_db_key
from app.repos.service_keys import hash_key
from app.settings import get_settings

bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="ServiceBearer",
    description=(
        "Service API key: `Authorization: Bearer <key>`. "
        "Bootstrap keys come from SERVICE_API_KEYS (full access); DB keys carry scopes."
    ),
)


def _env_key_principal(raw: str) -> Principal | None:
    settings = get_settings()
    keys = settings.service_key_set
    if not keys:
        return None
    ok = False
    for key in keys:
        ok = secrets.compare_digest(raw, key) or ok
    if not ok:
        return None
    return Principal(
        kind="service",
        id="env",
        is_superadmin=True,
        scopes=service_all_scopes(),
    )


async def service_auth_configured(session: AsyncSession) -> bool:
    """True when at least one env key or enabled DB key exists."""
    if get_settings().service_key_set:
        return True
    stmt = select(ServiceKey.id).where(ServiceKey.enabled.is_(True)).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def authenticate_service_key(
    raw: str, session: AsyncSession
) -> Principal | None:
    env_principal = _env_key_principal(raw)
    if env_principal is not None:
        return env_principal
    return await authenticate_db_key(session, raw)

