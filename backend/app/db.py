"""Async SQLAlchemy plumbing + automatic database creation."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.logging_setup import logger
from app.settings import get_settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Lazily create the engine so tests can swap DATABASE_URL."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def reset_engine() -> None:
    """Drop the cached engine (test helper)."""
    await dispose_engine()


def _maintenance_url(url: URL) -> URL:
    return url.set(database="postgres")


def _database_name(url: URL) -> str:
    return (url.database or "").strip()


async def ensure_database() -> bool:
    """Create the target PostgreSQL database if it does not exist.

    Runs before Alembic connects, so `alembic upgrade head` (Compose migrate
    container, k8s initContainer, local CLI) is the single bootstrapping path.
    Returns True when the database already existed, False when it was created.
    """
    url = make_url(get_settings().database_url)
    if not url.drivername.startswith("postgresql"):
        return True
    name = _database_name(url)
    if not name or name == "postgres":
        return True

    engine = create_async_engine(_maintenance_url(url), isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            )
            if exists:
                return True
            quoted = engine.dialect.identifier_preparer.quote(name)
            try:
                await conn.execute(text(f"CREATE DATABASE {quoted}"))
            except DBAPIError as exc:  # concurrent create from another replica
                if "already exists" not in str(exc).lower():
                    raise
                return True
            logger.info("Created database {!r}", name)
            return False
    except SQLAlchemyError:
        logger.exception("Could not ensure database {!r} exists", name)
        raise
    finally:
        await engine.dispose()
