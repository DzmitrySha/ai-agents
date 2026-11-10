"""Auth persistence: users and BFF sessions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuthSession, UserIdentity, utcnow
from app.settings import get_settings


def aware(value: datetime) -> datetime:
    """SQLite returns naive datetimes; normalize before comparing."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


async def upsert_user(
    session: AsyncSession,
    *,
    sub: str,
    email: str | None,
    display_name: str | None,
    roles: list[str],
    is_superadmin: bool,
) -> UserIdentity:
    emails = get_settings().superadmin_email_set
    if email and email.strip().lower() in emails:
        is_superadmin = True
    user = await session.get(UserIdentity, sub)
    now = utcnow()
    if user is None:
        user = UserIdentity(
            sub=sub,
            email=email,
            display_name=display_name,
            roles=roles,
            is_superadmin=is_superadmin,
            app_role="superadmin" if is_superadmin else "user",
            last_login_at=now,
        )
        session.add(user)
    else:
        user.email = email
        user.display_name = display_name
        user.roles = roles
        # IdP role/bootstrap may grant superadmin; a manual app-level grant
        # (app_role=superadmin) must survive subsequent logins.
        if is_superadmin or user.app_role == "superadmin":
            user.is_superadmin = True
            user.app_role = "superadmin"
        else:
            user.is_superadmin = False
        user.last_login_at = now
    await session.commit()
    await session.refresh(user)
    return user


async def create_session(
    session: AsyncSession, *, user_sub: str, ttl_hours: int
) -> AuthSession:
    row = AuthSession(
        user_sub=user_sub,
        expires_at=utcnow() + timedelta(hours=ttl_hours),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_session_row(session: AsyncSession, session_id: str) -> AuthSession | None:
    return await session.get(AuthSession, session_id)


async def revoke_session(session: AsyncSession, session_id: str) -> None:
    row = await session.get(AuthSession, session_id)
    if row is not None and not row.revoked:
        row.revoked = True
        await session.commit()


async def list_users(session: AsyncSession) -> list[UserIdentity]:
    stmt = select(UserIdentity).order_by(UserIdentity.created_at.desc())
    return list((await session.execute(stmt)).scalars())


async def get_user(session: AsyncSession, sub: str) -> UserIdentity | None:
    return await session.get(UserIdentity, sub)


async def create_user(
    session: AsyncSession,
    *,
    sub: str,
    email: str | None,
    display_name: str | None,
    app_role: str,
    daily_run_limit: int | None,
) -> UserIdentity:
    user = UserIdentity(
        sub=sub,
        email=email,
        display_name=display_name,
        roles=[],
        is_superadmin=app_role == "superadmin",
        app_role=app_role,
        daily_run_limit=daily_run_limit,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def update_user(
    session: AsyncSession,
    sub: str,
    *,
    app_role: str | None = None,
    daily_run_limit: int | None = None,
    set_daily_run_limit: bool = False,
) -> UserIdentity | None:
    user = await session.get(UserIdentity, sub)
    if user is None:
        return None
    if app_role is not None:
        user.app_role = app_role
        user.is_superadmin = app_role == "superadmin"
    if set_daily_run_limit:
        user.daily_run_limit = daily_run_limit
    await session.commit()
    await session.refresh(user)
    return user


async def promote_bootstrap_superadmins(session: AsyncSession) -> int:
    """SUPERADMIN_EMAILS всегда получают суперадминские права (при старте и логине)."""
    emails = get_settings().superadmin_email_set
    if not emails:
        return 0
    stmt = select(UserIdentity).where(
        func.lower(UserIdentity.email).in_(sorted(emails))
    )
    promoted = 0
    for user in (await session.execute(stmt)).scalars():
        if not user.is_superadmin or user.app_role != "superadmin":
            user.is_superadmin = True
            user.app_role = "superadmin"
            promoted += 1
    if promoted:
        await session.commit()
    return promoted
