"""Roles (superadmin/admin/user), scopes and per-user daily run quotas."""

from __future__ import annotations

from tests.conftest import AUTH

AGENT = {
    "slug": "shared-agent",
    "name": "Shared",
    "system_prompt": "p",
    "tools": [],
}


def _seed_published(client, slug: str = "shared-agent") -> None:
    created = client.post("/v1/agents", json={**AGENT, "slug": slug}, headers=AUTH)
    assert created.status_code == 201, created.text
    published = client.post(
        f"/v1/agents/{slug}/publish", json={"visibility": "shared"}, headers=AUTH
    )
    assert published.status_code == 200, published.text


def _fake_stream(monkeypatch) -> None:
    from app.agents.events import AgentEvent
    from app.runtime import manager as manager_module

    async def fake(config, prompt, run_override, max_steps):
        yield AgentEvent("message.delta", {"delta": "ok"})

    monkeypatch.setattr(manager_module, "stream_agent", fake)


def test_user_is_read_only(client, login):
    _seed_published(client)
    headers = login("viewer", app_role="user")

    assert client.get("/v1/agents", headers=headers).status_code == 200
    assert client.get("/v1/tools", headers=headers).status_code == 200
    assert client.get("/v1/agents/shared-agent", headers=headers).status_code == 200

    created = client.post(
        "/v1/agents",
        headers=headers,
        json={"slug": "mine", "name": "Mine", "system_prompt": "p"},
    )
    assert created.status_code == 403
    assert client.post(
        "/v1/agents/shared-agent/publish", headers=headers, json={"visibility": "shared"}
    ).status_code == 403
    assert client.patch(
        "/v1/agents/shared-agent", headers=headers, json={"name": "hack"}
    ).status_code == 403
    assert client.post(
        "/v1/tools",
        headers=headers,
        json={"slug": "x", "name": "x", "url": "https://a.test/x"},
    ).status_code == 403
    assert client.get("/api/admin/users", headers=headers).status_code == 403


def test_admin_manages_agents_but_not_access(client, login):
    headers = login("owner", app_role="admin")

    created = client.post(
        "/v1/agents",
        headers=headers,
        json={"slug": "admin-agent", "name": "Admin", "system_prompt": "p"},
    )
    assert created.status_code == 201
    assert created.json()["owner"]["id"] == "owner"
    assert client.post(
        "/v1/agents/admin-agent/publish", headers=headers, json={"visibility": "shared"}
    ).status_code == 200

    assert client.get("/api/admin/users", headers=headers).status_code == 403
    assert client.put(
        "/v1/settings/llm", headers=headers, json={"model": "x"}
    ).status_code == 403


def test_user_quota_limits_runs_per_day(client, login, monkeypatch):
    _seed_published(client)
    _fake_stream(monkeypatch)
    monkeypatch.setenv("USER_DAILY_RUN_LIMIT", "2")
    from app.settings import get_settings

    get_settings.cache_clear()

    headers = login("limited", app_role="user")
    first = client.post("/v1/runs", headers=headers, json={"agent_id": "shared-agent", "input": "1"})
    second = client.post("/v1/runs", headers=headers, json={"agent_id": "shared-agent", "input": "2"})
    third = client.post("/v1/runs", headers=headers, json={"agent_id": "shared-agent", "input": "3"})

    assert first.status_code == 201
    assert second.status_code == 201
    assert third.status_code == 429
    assert "daily run limit" in third.json()["detail"]


def test_admin_has_no_quota(client, login, monkeypatch):
    _seed_published(client)
    _fake_stream(monkeypatch)
    monkeypatch.setenv("USER_DAILY_RUN_LIMIT", "1")
    from app.settings import get_settings

    get_settings.cache_clear()

    headers = login("boss", app_role="admin")
    for index in range(3):
        response = client.post(
            "/v1/runs", headers=headers, json={"agent_id": "shared-agent", "input": str(index)}
        )
        assert response.status_code == 201, response.text


def test_superadmin_manages_users(client, login):
    admin = login("root", is_superadmin=True)

    created = client.post(
        "/api/admin/users",
        headers=admin,
        json={
            "sub": "pre-provisioned",
            "email": "pre@example.test",
            "app_role": "admin",
            "daily_run_limit": 5,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["app_role"] == "admin"
    assert created.json()["daily_run_limit"] == 5

    duplicate = client.post(
        "/api/admin/users", headers=admin, json={"sub": "pre-provisioned"}
    )
    assert duplicate.status_code == 409

    updated = client.patch(
        "/api/admin/users/pre-provisioned",
        headers=admin,
        json={"app_role": "user", "daily_run_limit": 1},
    )
    assert updated.status_code == 200
    assert updated.json()["app_role"] == "user"
    assert updated.json()["daily_run_limit"] == 1

    cleared = client.patch(
        "/api/admin/users/pre-provisioned", headers=admin, json={"daily_run_limit": None}
    )
    assert cleared.json()["daily_run_limit"] is None

    listed = client.get("/api/admin/users", headers=admin).json()
    assert any(item["id"] == "pre-provisioned" and item["runs_today"] == 0 for item in listed)

    assert client.patch(
        "/api/admin/users/ghost", headers=admin, json={"app_role": "user"}
    ).status_code == 404


def test_per_user_limit_overrides_env(client, login, monkeypatch):
    _seed_published(client)
    _fake_stream(monkeypatch)
    monkeypatch.setenv("USER_DAILY_RUN_LIMIT", "10")
    from app.settings import get_settings

    get_settings.cache_clear()

    root = login("root", is_superadmin=True)
    assert client.patch(
        "/api/admin/users/viewer2",
        headers=root,
        json={"app_role": "user", "daily_run_limit": 1},
    ).status_code == 404  # пользователь ещё не появлялся

    headers = login("viewer2", app_role="user")
    first = client.post("/v1/runs", headers=headers, json={"agent_id": "shared-agent", "input": "1"})
    assert first.status_code == 201

    root = login("root", is_superadmin=True)
    patched = client.patch(
        "/api/admin/users/viewer2", headers=root, json={"daily_run_limit": 1}
    )
    assert patched.status_code == 200

    headers = login("viewer2", app_role="user")
    # Лимит 1, один запуск уже был сегодня → следующий запрещён.
    blocked = client.post(
        "/v1/runs", headers=headers, json={"agent_id": "shared-agent", "input": "2"}
    )
    assert blocked.status_code == 429


def test_bootstrap_email_becomes_superadmin(run_db):
    async def _upsert():
        from app.db import get_session_factory
        from app.repos.auth import upsert_user

        async with get_session_factory()() as session:
            user = await upsert_user(
                session,
                sub="boot",
                email="admin@example.com",
                display_name="Boot",
                roles=[],
                is_superadmin=False,
            )
            return user.is_superadmin, user.app_role

    assert run_db(_upsert) == (True, "superadmin")


def test_startup_promotes_existing_bootstrap_email(run_db):
    async def _seed_and_promote():
        from app.db import get_session_factory
        from app.models import UserIdentity
        from app.repos.auth import promote_bootstrap_superadmins

        async with get_session_factory()() as session:
            session.add(
                UserIdentity(
                    sub="legacy",
                    email="Admin@Example.example.com",
                    roles=[],
                    is_superadmin=False,
                    app_role="admin",
                )
            )
            await session.commit()
            promoted = await promote_bootstrap_superadmins(session)
            user = await session.get(UserIdentity, "legacy")
            return promoted, user.is_superadmin, user.app_role

    promoted, is_superadmin, role = run_db(_seed_and_promote)
    assert promoted == 1
    assert is_superadmin is True
    assert role == "superadmin"


def test_identity_users_proxy(client, login, monkeypatch):
    from app.auth import directory
    from app.routers import admin as admin_router

    calls: list[tuple[str, int]] = []

    async def fake_search(query: str = "", limit: int = 20, first: int = 0):
        calls.append((query, limit, first))
        return {
            "items": [
                {
                    "sub": "kc-1",
                    "username": "ivanov",
                    "email": "ivanov@example.com",
                    "display_name": "Иван Иванов",
                    "enabled": True,
                }
            ],
            "has_more": False,
        }

    monkeypatch.setattr(admin_router.directory, "search_users", fake_search)
    root = login("root", is_superadmin=True)

    response = client.get("/api/admin/identity-users?q=ivan&limit=5&first=10", headers=root)

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "sub": "kc-1",
                "username": "ivanov",
                "email": "ivanov@example.com",
                "display_name": "Иван Иванов",
                "enabled": True,
            }
        ],
        "has_more": False,
    }
    assert calls == [("ivan", 5, 10)]

    plain = login("plain", app_role="admin")
    assert client.get("/api/admin/identity-users", headers=plain).status_code == 403

    async def failing(query: str = "", limit: int = 20, first: int = 0):
        raise directory.DirectoryError("клиенту не выдано право view-users (403)")

    monkeypatch.setattr(admin_router.directory, "search_users", failing)
    root = login("root", is_superadmin=True)
    broken = client.get("/api/admin/identity-users", headers=root)
    assert broken.status_code == 502
    assert "view-users" in broken.json()["detail"]


def test_app_role_superadmin_survives_missing_flag(client, login):
    headers = login("stale", is_superadmin=False, app_role="superadmin")

    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["user"]["is_superadmin"] is True
    assert me.json()["user"]["app_role"] == "superadmin"
    assert client.get("/api/admin/service-keys", headers=headers).status_code == 200


def test_upsert_user_keeps_app_role_superadmin(run_db):
    async def _run():
        from app.db import get_session_factory
        from app.repos.auth import create_user, upsert_user

        async with get_session_factory()() as session:
            await create_user(
                session,
                sub="manual",
                email=None,
                display_name="Manual",
                app_role="superadmin",
                daily_run_limit=None,
            )
            user = await upsert_user(
                session,
                sub="manual",
                email=None,
                display_name="Manual",
                roles=[],
                is_superadmin=False,
            )
            return user.is_superadmin, user.app_role

    assert run_db(_run) == (True, "superadmin")

