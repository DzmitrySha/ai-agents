"""Auth: open health, service Bearer, cookie+CSRF, admin gate."""

from __future__ import annotations

from tests.conftest import AUTH

AGENT_PAYLOAD = {
    "slug": "auth-agent",
    "name": "Auth agent",
    "system_prompt": "hello",
    "tools": [],
}


def test_health_is_open(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_missing_key_is_401(client):
    assert client.get("/v1/agents").status_code == 401


def test_wrong_key_is_401(client):
    response = client.get("/v1/agents", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401


def test_non_bearer_scheme_is_401(client):
    response = client.get("/v1/agents", headers={"Authorization": "Basic test-key"})
    assert response.status_code == 401


def test_valid_env_key_is_200(client):
    assert client.get("/v1/agents", headers=AUTH).status_code == 200


def test_unconfigured_service_auth_is_503(client, monkeypatch):
    from app.settings import get_settings

    monkeypatch.setenv("SERVICE_API_KEYS", "")
    get_settings.cache_clear()
    response = client.get("/v1/agents", headers=AUTH)
    assert response.status_code == 503


def test_cookie_mutation_requires_csrf_header(client, login):
    headers = login("u1")
    denied = client.post("/v1/agents", json=AGENT_PAYLOAD, headers={})
    assert denied.status_code == 403

    created = client.post("/v1/agents", json=AGENT_PAYLOAD, headers=headers)
    assert created.status_code == 201
    assert created.json()["owner"]["id"] == "u1"


def test_me_returns_user_and_revoked_session_is_401(client, login, run_db):
    headers = login("u1")
    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["user"]["id"] == "u1"
    assert me.json()["user"]["is_superadmin"] is False

    async def revoke_all() -> None:
        from sqlalchemy import update

        from app.db import get_session_factory
        from app.models import AuthSession

        async with get_session_factory()() as session:
            await session.execute(update(AuthSession).values(revoked=True))
            await session.commit()

    run_db(revoke_all)
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_admin_requires_superadmin(client, login):
    user_headers = login("plain")
    assert client.get("/api/admin/users", headers=user_headers).status_code == 403

    admin_headers = login("root", is_superadmin=True)
    response = client.get("/api/admin/users", headers=admin_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list) and len(response.json()) >= 1

    created = client.post(
        "/api/admin/service-keys",
        headers=admin_headers,
        json={"name": "ci", "scopes": ["runs:read"]},
    )
    assert created.status_code == 201
    assert created.json()["key"].startswith("sk-ag-")

    listed = client.get("/api/admin/service-keys", headers=admin_headers).json()
    assert any(item["name"] == "ci" for item in listed)
    key_id = created.json()["id"]
    revoked = client.post(
        f"/api/admin/service-keys/{key_id}/revoke", headers=admin_headers
    )
    assert revoked.status_code == 200
    assert revoked.json()["enabled"] is False


def test_service_key_scopes_can_change_and_key_can_be_restored(client, login):
    admin_headers = login("root", is_superadmin=True)
    created = client.post(
        "/api/admin/service-keys",
        headers=admin_headers,
        json={"name": "rotating", "scopes": ["runs:read"]},
    ).json()
    key_id = created["id"]
    bearer = {"Authorization": f"Bearer {created['key']}"}

    patched = client.patch(
        f"/api/admin/service-keys/{key_id}",
        headers=admin_headers,
        json={"scopes": ["agents:read"]},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["scopes"] == ["agents:read"]
    assert client.get("/v1/agents", headers=bearer).status_code == 200
    assert client.get("/v1/runs", headers=bearer).status_code == 403

    assert (
        client.post(
            f"/api/admin/service-keys/{key_id}/revoke", headers=admin_headers
        ).status_code
        == 200
    )
    assert client.get("/v1/agents", headers=bearer).status_code == 401

    restored = client.patch(
        f"/api/admin/service-keys/{key_id}",
        headers=admin_headers,
        json={"enabled": True},
    )
    assert restored.status_code == 200
    assert restored.json()["enabled"] is True
    assert client.get("/v1/agents", headers=bearer).status_code == 200


def test_created_service_key_authenticates(client, login):
    admin_headers = login("root", is_superadmin=True)
    created = client.post(
        "/api/admin/service-keys",
        headers=admin_headers,
        json={"name": "reader", "scopes": ["agents:read"]},
    ).json()
    bearer = {"Authorization": f"Bearer {created['key']}"}
    assert client.get("/v1/agents", headers=bearer).status_code == 200
    assert client.get("/v1/tools", headers=bearer).status_code == 200
    assert client.get("/v1/runs", headers=bearer).status_code == 403



def test_login_is_503_without_oidc_client(client):
    assert client.get("/auth/login").status_code == 503


def test_oidc_roles_and_return_to_are_sanitized():
    from app.auth.oidc import _roles, _safe_return_to

    claims = {
        "sub": "u1",
        "realm_access": {"roles": ["ai-agents-admin", "offline_access"]},
        "resource_access": {"ai-agents": {"roles": ["runs:write"]}},
    }
    assert _roles(claims, "", "ai-agents") == [
        "ai-agents-admin",
        "offline_access",
        "runs:write",
    ]
    assert _safe_return_to("/agents?x=1") == "/agents?x=1"
    assert _safe_return_to("//evil.example") == "/agents"
    assert _safe_return_to("https://evil.example") == "/agents"
    assert _safe_return_to(None) == "/agents"
