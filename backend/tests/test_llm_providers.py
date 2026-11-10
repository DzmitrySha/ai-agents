"""Named LLM providers: CRUD, active pointer, cache refresh, permissions."""

from __future__ import annotations

from tests.conftest import AUTH

PROVIDER = {
    "name": "lm-studio",
    "base_url": "http://llm.local:1234/v1",
    "model": "qwen3.5-4b",
    "api_key": "sk-secret",
}


def test_provider_crud_and_active(client, login):
    root = login("root", is_superadmin=True)

    created = client.post("/v1/settings/llm/providers", headers=root, json=PROVIDER)
    assert created.status_code == 201, created.text
    body = created.json()
    provider_id = body["id"]
    assert body["name"] == "lm-studio"
    assert body["api_key_set"] is True
    assert body["api_key_hint"] == "…cret"
    assert "sk-secret" not in created.text

    duplicate = client.post(
        "/v1/settings/llm/providers", headers=root, json=PROVIDER
    )
    assert duplicate.status_code == 409

    listed = client.get("/v1/settings/llm/providers", headers=root).json()
    assert [item["name"] for item in listed["items"]] == ["lm-studio"]
    assert listed["active_id"] is None
    assert listed["effective"]["source"] == "env"

    activated = client.put(
        "/v1/settings/llm/active", headers=root, json={"provider_id": provider_id}
    )
    assert activated.status_code == 200
    assert activated.json()["active_id"] == provider_id
    assert activated.json()["effective"]["source"] == "provider"
    assert activated.json()["effective"]["base_url"] == PROVIDER["base_url"]
    assert activated.json()["effective"]["model"] == PROVIDER["model"]

    from app.runtime.llm_config import project_llm

    assert project_llm().base_url == PROVIDER["base_url"]
    assert project_llm().model == PROVIDER["model"]

    patched = client.patch(
        f"/v1/settings/llm/providers/{provider_id}",
        headers=root,
        json={"model": "qwen3.5-8b", "clear_api_key": True},
    )
    assert patched.status_code == 200
    assert patched.json()["model"] == "qwen3.5-8b"
    assert patched.json()["api_key_set"] is False

    deleted = client.delete(f"/v1/settings/llm/providers/{provider_id}", headers=root)
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "active_id": None}

    after = client.get("/v1/settings/llm/providers", headers=root).json()
    assert after["items"] == []
    assert after["effective"]["source"] == "env"


def test_provider_requires_superadmin(client, login):
    admin = login("boss", app_role="admin")
    denied = client.post("/v1/settings/llm/providers", headers=admin, json=PROVIDER)
    assert denied.status_code == 403

    viewer = login("viewer", app_role="user")
    assert client.get("/v1/settings/llm/providers", headers=viewer).status_code == 200


def test_active_provider_must_exist(client, login):
    root = login("root", is_superadmin=True)
    missing = client.put(
        "/v1/settings/llm/active", headers=root, json={"provider_id": "ghost"}
    )
    assert missing.status_code == 404

    cleared = client.put(
        "/v1/settings/llm/active", headers=root, json={"provider_id": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["active_id"] is None


def test_models_endpoint_uses_active_provider(client, login, monkeypatch):
    from app.routers import settings as settings_router

    calls: list[tuple[str, str | None]] = []

    async def fake_fetch(base_url: str, api_key: str | None, **_auth) -> list[str]:
        calls.append((base_url, api_key))
        return ["qwen3.5-4b"]

    monkeypatch.setattr(settings_router, "fetch_models", fake_fetch)

    root = login("root", is_superadmin=True)
    created = client.post("/v1/settings/llm/providers", headers=root, json=PROVIDER).json()
    client.put(
        "/v1/settings/llm/active",
        headers=root,
        json={"provider_id": created["id"]},
    )

    response = client.post("/v1/settings/llm/models", headers=AUTH, json={})

    assert response.status_code == 200
    assert calls[-1] == (PROVIDER["base_url"], PROVIDER["api_key"])
