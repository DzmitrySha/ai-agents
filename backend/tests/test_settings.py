"""Project-wide LLM settings: env fallback, masking, admin-only writes, model probe."""

from __future__ import annotations

from tests.conftest import AUTH


def test_settings_default_to_env_and_mask_key(client):
    response = client.get("/v1/settings/llm", headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["base_url"] == "http://localhost:9/v1"
    assert body["model"] == "test-model"
    assert body["source"] == "env"
    # env `DEFAULT_LLM_API_KEY` в тестах не задан → "not-needed" не считается ключом
    assert body["api_key_set"] is False
    assert body["api_key_hint"] is None


def test_settings_write_requires_admin(client, login):
    user_headers = login("plain")
    denied = client.put(
        "/v1/settings/llm", headers=user_headers, json={"model": "qwen"}
    )
    assert denied.status_code == 403

    admin_headers = login("root", is_superadmin=True)
    saved = client.put(
        "/v1/settings/llm",
        headers=admin_headers,
        json={
            "base_url": "http://llm.local:1234/v1",
            "model": "qwen3.5-4b",
            "api_key": "sk-secret-value",
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["source"] == "db"
    assert body["api_key_set"] is True
    assert body["api_key_hint"] == "…alue"
    assert "sk-secret-value" not in saved.text

    reread = client.get("/v1/settings/llm", headers=AUTH).json()
    assert reread["base_url"] == "http://llm.local:1234/v1"
    assert reread["model"] == "qwen3.5-4b"

    # Пустой ключ не затирает сохранённый, а флаг clear_api_key — затирает.
    untouched = client.put(
        "/v1/settings/llm", headers=admin_headers, json={"model": "qwen3.5-4b"}
    ).json()
    assert untouched["api_key_set"] is True
    cleared = client.put(
        "/v1/settings/llm", headers=admin_headers, json={"clear_api_key": True}
    ).json()
    assert cleared["api_key_set"] is False


def test_settings_reject_non_http_base_url(client, login):
    admin_headers = login("root", is_superadmin=True)
    response = client.put(
        "/v1/settings/llm", headers=admin_headers, json={"base_url": "llm.local:1234"}
    )
    assert response.status_code == 422


def test_saved_settings_feed_project_llm_cache(client, login):
    from app.runtime.llm_config import project_llm

    admin_headers = login("root", is_superadmin=True)
    client.put(
        "/v1/settings/llm",
        headers=admin_headers,
        json={"base_url": "http://llm.local:9999/v1", "model": "cached-model"},
    )

    config = project_llm()
    assert config.base_url == "http://llm.local:9999/v1"
    assert config.model == "cached-model"


def test_models_endpoint_uses_provider(client, monkeypatch):
    from app.routers import settings as settings_router

    calls: list[tuple[str, str | None]] = []

    async def fake_fetch(base_url: str, api_key: str | None, **_auth) -> list[str]:
        calls.append((base_url, api_key))
        return ["qwen3.5-4b", "llama-3.1-8b"]

    monkeypatch.setattr(settings_router, "fetch_models", fake_fetch)

    response = client.post(
        "/v1/settings/llm/models",
        headers=AUTH,
        json={"base_url": "http://llm.local:1234/v1", "api_key": "sk-test"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "base_url": "http://llm.local:1234/v1",
        "models": ["qwen3.5-4b", "llama-3.1-8b"],
    }
    assert calls == [("http://llm.local:1234/v1", "sk-test")]


def test_models_endpoint_maps_provider_failure_to_502(client, monkeypatch):
    from app.routers import settings as settings_router
    from app.runtime.llm_config import ModelsError

    async def fake_fetch(base_url: str, api_key: str | None, **_auth) -> list[str]:
        raise ModelsError("HTTP 401 от http://llm.local/models: unauthorized")

    monkeypatch.setattr(settings_router, "fetch_models", fake_fetch)

    response = client.post(
        "/v1/settings/llm/models", headers=AUTH, json={"base_url": "http://llm.local/v1"}
    )

    assert response.status_code == 502
    assert "401" in response.json()["detail"]


def test_models_requires_auth(client):
    assert client.post("/v1/settings/llm/models", json={}).status_code == 401
