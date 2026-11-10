"""Read-only platform doctor: DB, migrations, LLM, MCP, auth, storage, queue."""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text

from app.agents.mcp_client import list_remote_tools
from app.models import McpConnection, RunRow
from app.repos import approvals as approvals_repo
from app.repos.runs import count_queued_runs, oldest_queued_at
from app.redaction import redact_text
from app.runtime.llm_config import fetch_models, project_llm
from app.runtime.models import DoctorCheck, DoctorResult, utcnow
from app.runtime.retention import last_retention_at
from app.settings import Settings

MCP_TIMEOUT_SECONDS = 12.0
WEAK_SECRETS = frozenset({"", "dev-only-change-me", "change-me", "secret"})


async def _timed(
    check_id: str, factory: Callable[[], Awaitable[DoctorCheck]]
) -> DoctorCheck:
    started = time.perf_counter()
    try:
        check = await factory()
    except Exception as exc:  # noqa: BLE001 - each check reports independently
        check = DoctorCheck(
            id=check_id,
            status="error",
            message=redact_text(f"{type(exc).__name__}: {exc}"),
        )
    check.duration_ms = int((time.perf_counter() - started) * 1000)
    return check


async def _check_db(session_factory) -> DoctorCheck:
    async with session_factory() as session:
        await session.execute(text("SELECT 1"))
    return DoctorCheck(id="db", status="ok", message="database reachable")


async def _check_migrations(session_factory) -> DoctorCheck:
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    expected = set(ScriptDirectory.from_config(config).get_heads())
    async with session_factory() as session:
        current = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one_or_none()
    if current not in expected:
        return DoctorCheck(
            id="migrations",
            status="error",
            message=f"database revision {current!r}, expected one of {sorted(expected)}",
            details={"current": current, "heads": sorted(expected)},
        )
    return DoctorCheck(
        id="migrations",
        status="ok",
        message=f"revision {current}",
        details={"current": current, "heads": sorted(expected)},
    )


async def _check_llm() -> DoctorCheck:
    config = project_llm()
    models = await fetch_models(
        config.base_url or "",
        config.api_key,
        auth_type=config.auth_type,
        auth_header=config.auth_header,
        auth_prefix=config.auth_prefix,
    )
    if config.model and config.model not in models:
        return DoctorCheck(
            id="llm",
            status="warn",
            message=f"model {config.model} is not listed",
            details={"model": config.model, "models": len(models)},
        )
    return DoctorCheck(
        id="llm",
        status="ok",
        message=f"{len(models)} models",
        details={"model": config.model, "models": len(models)},
    )


async def _check_mcp(session_factory) -> DoctorCheck:
    async with session_factory() as session:
        rows = list(
            (
                await session.execute(
                    select(McpConnection).where(McpConnection.enabled.is_(True))
                )
            ).scalars()
        )
    if not rows:
        return DoctorCheck(id="mcp", status="ok", message="no MCP connections")
    errors: list[str] = []
    for row in rows:
        try:
            await asyncio.wait_for(
                list_remote_tools(
                    row.url,
                    dict(row.headers or {}),
                    min(float(row.timeout_seconds), MCP_TIMEOUT_SECONDS),
                ),
                timeout=MCP_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001 - report each connection
            errors.append(f"{row.slug}: {type(exc).__name__}: {exc}")
    if errors:
        return DoctorCheck(
            id="mcp",
            status="warn",
            message=f"{len(errors)} of {len(rows)} connections failed",
            details={"connections": len(rows), "errors": errors},
        )
    return DoctorCheck(
        id="mcp",
        status="ok",
        message=f"{len(rows)} connections",
        details={"connections": len(rows)},
    )


def _check_auth(settings: Settings) -> DoctorCheck:
    oidc = settings.oidc_enabled
    keys = bool(settings.service_key_set)
    weak_secret = (settings.session_secret_key or "").strip().lower() in WEAK_SECRETS
    if not oidc and not keys:
        return DoctorCheck(
            id="auth",
            status="error",
            message="neither OIDC nor service keys configured",
        )
    if weak_secret:
        return DoctorCheck(
            id="auth",
            status="warn",
            message="weak SESSION_SECRET_KEY",
            details={"oidc": oidc, "service_keys": keys},
        )
    return DoctorCheck(
        id="auth",
        status="ok",
        message="OIDC/service keys configured",
        details={"oidc": oidc, "service_keys": keys},
    )


def _check_storage(settings: Settings) -> DoctorCheck:
    raw = (settings.storage_path or "").strip()
    if not raw:
        return DoctorCheck(id="storage", status="skip", message="STORAGE_PATH is empty")
    path = Path(raw)
    if not path.exists():
        return DoctorCheck(
            id="storage", status="error", message=f"path does not exist: {raw}"
        )
    usage = shutil.disk_usage(path)
    details = {
        "path": raw,
        "writable": os.access(path, os.W_OK),
        "free_gb": round(usage.free / (1024**3), 1),
    }
    if usage.free < 1024**3:
        return DoctorCheck(
            id="storage",
            status="warn",
            message="less than 1 GiB free",
            details=details,
        )
    return DoctorCheck(
        id="storage", status="ok", message=f"{details['free_gb']} GiB free", details=details
    )


async def _check_queue(session_factory, manager) -> DoctorCheck:
    async with session_factory() as session:
        queued = await count_queued_runs(session)
        oldest = await oldest_queued_at(session)
    oldest_seconds = (
        max(0, int((utcnow() - _aware(oldest)).total_seconds()))
        if oldest is not None
        else None
    )
    details: dict[str, Any] = {
        "queued": queued,
        "oldest_seconds": oldest_seconds,
        **manager.gate_snapshot(),
    }
    if oldest_seconds is not None and oldest_seconds > 300:
        return DoctorCheck(
            id="queue",
            status="warn",
            message=f"oldest queued run is {oldest_seconds}s old",
            details=details,
        )
    return DoctorCheck(
        id="queue", status="ok", message=f"{queued} queued", details=details
    )


def _check_retention(settings: Settings) -> DoctorCheck:
    last = last_retention_at()
    if last is None:
        return DoctorCheck(
            id="retention",
            status="warn",
            message="retention has not run yet",
            details={"interval_seconds": settings.run_retention_interval_seconds},
        )
    age = max(0, int((utcnow() - _aware(last)).total_seconds()))
    limit = max(60, settings.run_retention_interval_seconds) * 2
    details = {"last_run_seconds_ago": age, "limit_seconds": limit}
    if age > limit:
        return DoctorCheck(
            id="retention",
            status="warn",
            message=f"retention is stale ({age}s)",
            details=details,
        )
    return DoctorCheck(
        id="retention", status="ok", message=f"last run {age}s ago", details=details
    )


async def _check_approvals(session_factory) -> DoctorCheck:
    async with session_factory() as session:
        pending = await approvals_repo.pending_count(session)
    return DoctorCheck(
        id="approvals",
        status="ok",
        message=f"{pending} pending",
        details={"pending": pending},
    )


async def _check_runs(session_factory) -> DoctorCheck:
    since = utcnow() - timedelta(hours=24)
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(RunRow.failure_kind, func.count())
                .where(RunRow.status == "failed", RunRow.created_at >= since)
                .group_by(RunRow.failure_kind)
            )
        ).all()
    by_kind = {str(kind or "unknown"): int(count) for kind, count in rows}
    total = sum(by_kind.values())
    return DoctorCheck(
        id="runs",
        status="ok",
        message=f"{total} failed in 24h",
        details={"failed_24h": total, "by_failure_kind": by_kind},
    )


async def run_doctor(session_factory, settings: Settings, manager) -> DoctorResult:
    checks = [
        await _timed("db", lambda: _check_db(session_factory)),
        await _timed("migrations", lambda: _check_migrations(session_factory)),
        await _timed("llm", _check_llm),
        await _timed("mcp", lambda: _check_mcp(session_factory)),
        await _timed("auth", lambda: _sync(_check_auth(settings))),
        await _timed("storage", lambda: _sync(_check_storage(settings))),
        await _timed("queue", lambda: _check_queue(session_factory, manager)),
        await _timed("retention", lambda: _sync(_check_retention(settings))),
        await _timed("approvals", lambda: _check_approvals(session_factory)),
        await _timed("runs", lambda: _check_runs(session_factory)),
    ]
    return DoctorResult(ok=not any(item.status == "error" for item in checks), checks=checks)


async def _sync(check: DoctorCheck) -> DoctorCheck:
    return check


def _aware(value):
    from app.repos.auth import aware

    return aware(value)
