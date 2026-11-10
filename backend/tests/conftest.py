"""Shared fixtures: temp SQLite DB, app, cookie login helpers."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from itsdangerous import URLSafeSerializer

AUTH = {"Authorization": "Bearer test-key"}
CSRF_HEADERS = {"X-Requested-With": "ai-agents-ui"}


@pytest.fixture
def settings(tmp_path, monkeypatch):
    db_path = (tmp_path / "test.db").as_posix()
    env = {
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
        "SERVICE_API_KEYS": "test-key",
        "DEFAULT_LLM_BASE_URL": "http://localhost:9/v1",
        "DEFAULT_LLM_MODEL": "test-model",
        "PUBLIC_URL": "http://testserver",
        "ENVIRONMENT": "test",
        "KEYCLOAK_CLIENT_SECRET": "",
        "SESSION_SECRET_KEY": "test-secret",
        "SESSION_COOKIE_SECURE": "false",
        "MAX_STEPS": "8",
        "MAX_STEPS_CAP": "32",
        "RUN_TIMEOUT_SECONDS": "30",
        "RUN_TIMEOUT_CAP_SECONDS": "600",
        "RUN_TOKEN_BUDGET": "200000",
        "RUN_TOKEN_CAP": "2000000",
        "RUN_MAX_ATTEMPTS": "2",
        "RUN_MAX_ATTEMPTS_CAP": "5",
        "RUN_RETRY_BACKOFF_SECONDS": "0",
        "RUN_RETRY_BACKOFF_MAX_SECONDS": "0",
        "RUN_FALLBACK_MODEL": "",
        "RUN_APPROVAL_MODE": "never",
        "RUN_APPROVAL_TIMEOUT_SECONDS": "60",
        "RUN_CONTEXT_MAX_TOKENS": "24000",
        "RUN_TOOL_OUTPUT_MAX_CHARS": "8000",
        "RUN_MAX_CONCURRENCY": "4",
        "RUN_MAX_CONCURRENCY_PER_AGENT": "2",
        "RUN_MAX_QUEUED": "50",
        "USER_DAILY_TOKEN_LIMIT": "0",
        "RUN_EVENTS_RETENTION_DAYS": "30",
        "RUN_RETENTION_INTERVAL_SECONDS": "60",
        "RUN_SCHEDULER_ENABLED": "false",
        "RUN_DELIVERY_ENABLED": "false",
        "LOG_DIR": str(tmp_path / "logs"),
        # Изоляция от локальных docker/.env(.secrets): только monkeypatch env.
        "SETTINGS_ENV_FILE": "",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    from app.settings import Settings, get_settings

    get_settings.cache_clear()
    yield Settings(_env_file=None)
    get_settings.cache_clear()


@pytest.fixture
def db(settings):
    """Create the schema once per test; the engine is rebound per event loop."""
    from app.db import get_engine, reset_engine
    from app.models import Base

    async def prepare() -> None:
        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await reset_engine()

    asyncio.run(prepare())
    yield
    asyncio.run(reset_engine())


@pytest.fixture
def client(db, settings):
    from app.main import create_app

    with TestClient(create_app(settings)) as test_client:
        yield test_client


def insert_stale_run(run_id: str, *, status: str = "running") -> None:
    """Seed a run left behind by a crash (single-loop helper)."""

    async def _insert() -> None:
        from app.db import get_session_factory, reset_engine
        from app.models import RunRow

        async with get_session_factory()() as session:
            session.add(
                RunRow(
                    id=run_id,
                    agent_slug="ghost",
                    status=status,
                    input="hi",
                    principal_kind="service",
                    principal_id="env",
                    tenant_id="default",
                )
            )
            await session.commit()
        await reset_engine()

    asyncio.run(_insert())


async def _make_session(
    sub: str,
    is_superadmin: bool,
    roles: list[str],
    app_role: str = "admin",
    email: str | None = None,
) -> str:
    from app.db import get_session_factory
    from app.models import AuthSession, UserIdentity, utcnow

    async with get_session_factory()() as session:
        user = await session.get(UserIdentity, sub)
        if user is None:
            user = UserIdentity(
                sub=sub,
                email=email or f"{sub}@example.test",
                display_name=sub,
                roles=roles,
                is_superadmin=is_superadmin,
                app_role="superadmin" if is_superadmin else app_role,
            )
            session.add(user)
            await session.commit()
        auth_session = AuthSession(
            user_sub=sub, expires_at=utcnow() + timedelta(hours=1)
        )
        session.add(auth_session)
        await session.commit()
        await session.refresh(auth_session)
        return auth_session.id


@pytest.fixture
def login(client, settings):
    signer = URLSafeSerializer(settings.session_secret_key, salt=settings.session_salt)

    def _login(
        sub: str = "u1",
        *,
        is_superadmin: bool = False,
        roles=(),
        app_role: str = "admin",
        email: str | None = None,
    ) -> dict:
        session_id = client.portal.call(
            _make_session, sub, is_superadmin, list(roles), app_role, email
        )
        client.cookies.clear()
        client.cookies.set(settings.session_cookie_name, signer.dumps(session_id))
        return dict(CSRF_HEADERS)

    return _login


@pytest.fixture
def run_db(client):
    def _run(func, *args):
        return client.portal.call(func, *args)

    return _run


@pytest.fixture
def fake_graph(monkeypatch):
    """Patch the ReAct graph so runs never touch a real LLM."""
    from types import SimpleNamespace

    from app.agents import execution

    class _FakeGraph:
        def __init__(
            self,
            deltas=("hello", " world"),
            steps=1,
            failure=None,
            usage=None,
            failures=None,
        ):
            self.deltas = deltas
            self.steps = steps
            self.failure = failure
            self.usage = usage
            self.failures = list(failures or [])

        async def astream_events(self, inputs, version="v2", config=None):
            if self.failures:
                failure = self.failures.pop(0)
                if failure is not None:
                    raise failure
            if self.failure:
                raise self.failure
            for delta in self.deltas:
                yield {
                    "event": "on_chat_model_stream",
                    "name": "model",
                    "data": {"chunk": SimpleNamespace(content=delta)},
                }
            yield {
                "event": "on_tool_start",
                "name": "calculator",
                "data": {"input": {"expression": "1+1"}},
            }
            yield {
                "event": "on_tool_end",
                "name": "calculator",
                "data": {"output": SimpleNamespace(content="2")},
            }
            for index in range(self.steps):
                yield {
                    "event": "on_chat_model_end",
                    "name": "model",
                    "data": {
                        "step": index,
                        "output": SimpleNamespace(
                            usage_metadata=self.usage, response_metadata={}
                        ),
                    },
                }

    state = {"graph": _FakeGraph()}

    def _fake_create_react_agent(*args, **kwargs):
        return state["graph"]

    monkeypatch.setattr(execution, "build_llm", lambda *a, **k: object())
    monkeypatch.setattr(execution, "create_react_agent", _fake_create_react_agent)

    def _set(**kwargs):
        state["graph"] = _FakeGraph(**kwargs)
        return state["graph"]

    _set.klass = _FakeGraph
    return _set
