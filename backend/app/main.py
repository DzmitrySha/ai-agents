"""FastAPI app: agent control plane (OIDC BFF + service keys)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from app.auth.deps import SessionDep
from app.agents.execution import configure_langfuse
from app.agents.mcp_server import build_mcp_asgi, build_mcp_server
from app.auth.oidc import register_oidc_client
from app.auth.oidc import router as auth_router
from app.db import dispose_engine, get_session_factory
from app.logging_setup import configure_logging, logger
from app.repos import auth as auth_repo
from app.repos import usage as usage_repo
from app.repos.runs import recover_stale_runs
from app.runtime.llm_config import refresh as refresh_llm_config
from app.runtime.usage_asgi import UsageMiddleware
from app.routers import (
    admin_router,
    agents_router,
    assist_router,
    catalog_router,
    doctor_router,
    mcp_connections_router,
    mcp_servers_router,
    memory_router,
    notifications_router,
    packs_router,
    runs_router,
    schedules_router,
    settings_router,
    skills_router,
    stats_router,
    tools_router,
)
from app.runtime.delivery import delivery_loop
from app.runtime.manager import RunManager
from app.runtime.retention import retention_loop
from app.runtime.scheduler import schedule_loop
from app.runtime.store import LiveHub
from app.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level="INFO", logs_dir=settings.log_dir)

    session_factory = get_session_factory()
    hub = LiveHub()
    manager = RunManager(hub, settings)
    mcp_server = build_mcp_server(
        session_factory=session_factory, manager=manager, settings=settings
    )
    mcp_app = build_mcp_asgi(mcp_server, settings, session_factory)
    register_oidc_client(settings)
    configure_langfuse(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info(
            "App start: app={} env={} oidc={} llm={}/{}",
            settings.app_name,
            settings.environment,
            settings.oidc_enabled,
            settings.default_llm_base_url,
            settings.default_llm_model,
        )
        async with session_factory() as session:
            recovered = await recover_stale_runs(session)
            config = await refresh_llm_config(session)
        if recovered:
            logger.warning("Marked {} stale run(s) as failed", recovered)
        try:
            async with session_factory() as session:
                promoted = await auth_repo.promote_bootstrap_superadmins(session)
            if promoted:
                logger.info("Promoted {} bootstrap superadmin(s)", promoted)
        except Exception as exc:  # noqa: BLE001 - bootstrap must not block startup
            logger.warning("Bootstrap superadmin promotion skipped: {}", exc)
        try:
            async with session_factory() as session:
                purged = await usage_repo.purge(session)
            if purged:
                logger.info("Purged {} usage rows older than 180d", purged)
        except Exception as exc:  # noqa: BLE001 - retention must not block startup
            logger.warning("Usage retention skipped: {}", exc)
        logger.info("LLM endpoint: {}/{}", config.base_url, config.model)
        retention_task = asyncio.create_task(
            retention_loop(session_factory, settings)
        )
        background_tasks = [retention_task]
        if settings.run_scheduler_enabled:
            background_tasks.append(
                asyncio.create_task(schedule_loop(session_factory, manager, settings))
            )
        if settings.run_delivery_enabled:
            background_tasks.append(
                asyncio.create_task(delivery_loop(session_factory, settings))
            )
        try:
            async with mcp_server.session_manager.run():
                yield
        finally:
            for task in background_tasks:
                task.cancel()
            await asyncio.gather(*background_tasks, return_exceptions=True)
            await manager.shutdown()
            await dispose_engine()
            logger.info("App stop")

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.run_manager = manager
    app.state.mcp_server = mcp_server

    https_only = settings.session_cookie_secure or settings.public_url.startswith(
        "https://"
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret_key,
        same_site="lax",
        https_only=https_only,
    )
    app.add_middleware(UsageMiddleware, session_factory=session_factory)

    app.include_router(auth_router)
    app.include_router(agents_router)
    app.include_router(assist_router)
    app.include_router(runs_router)
    app.include_router(schedules_router)
    app.include_router(tools_router)
    app.include_router(catalog_router)
    app.include_router(doctor_router)
    app.include_router(skills_router)
    app.include_router(settings_router)
    app.include_router(stats_router)
    app.include_router(mcp_connections_router)
    app.include_router(mcp_servers_router)
    app.include_router(memory_router)
    app.include_router(notifications_router)
    app.include_router(packs_router)
    app.include_router(admin_router)

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "app": settings.app_name,
            "environment": settings.environment,
        }

    @app.get("/health/db")
    async def health_db(session: AsyncSession = Depends(SessionDep)) -> dict:
        await session.execute(text("SELECT 1"))
        return {"status": "ok", "database": "up"}

    # Mounted last: `/mcp` and its RFC 9728 metadata route keep their exact paths,
    # every known FastAPI route above still matches first.
    app.mount("/", mcp_app)

    return app


app = create_app()
