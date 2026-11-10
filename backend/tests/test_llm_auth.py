"""LLM provider auth scheme: header/prefix choice reaches the wire."""

from __future__ import annotations

import httpx

PROVIDER = {
    "name": "gateway",
    "base_url": "http://llm.local:1234/v1",
    "model": "qwen3.5-4b",
    "api_key": "sk-secret",
}


def test_auth_headers_matrix():
    from app.runtime.llm_config import auth_headers

    assert auth_headers("k") == {"Authorization": "Bearer k"}
    assert auth_headers("k", "bearer", "Authorization", "") == {"Authorization": "k"}
    assert auth_headers("k", "header", "x-api-key", "") == {"x-api-key": "k"}
    assert auth_headers("k", "header", "X-Token", "Token ") == {"X-Token": "Token k"}
    assert auth_headers("k", "none") == {}
    assert auth_headers("") == {}
    assert auth_headers("not-needed") == {}


def test_provider_auth_scheme_roundtrip(client, login):
    root = login("root", is_superadmin=True)
    created = client.post(
        "/v1/settings/llm/providers",
        headers=root,
        json={
            **PROVIDER,
            "auth_type": "header",
            "auth_header": "x-api-key",
            "auth_prefix": "",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["auth_type"] == "header"
    assert body["auth_header"] == "x-api-key"
    assert body["auth_prefix"] == ""
    assert "sk-secret" not in created.text

    patched = client.patch(
        f"/v1/settings/llm/providers/{body['id']}",
        headers=root,
        json={"auth_type": "bearer", "auth_prefix": "Token "},
    ).json()
    assert patched["auth_type"] == "bearer"
    assert patched["auth_prefix"] == "Token "
    assert patched["auth_header"] == "x-api-key"

    bad_header = client.patch(
        f"/v1/settings/llm/providers/{body['id']}",
        headers=root,
        json={"auth_header": "bad header!"},
    )
    assert bad_header.status_code == 422


def test_active_provider_auth_reaches_chat_client(client, login):
    root = login("root", is_superadmin=True)
    created = client.post(
        "/v1/settings/llm/providers",
        headers=root,
        json={
            **PROVIDER,
            "auth_type": "header",
            "auth_header": "x-api-key",
            "auth_prefix": "",
        },
    ).json()
    activated = client.put(
        "/v1/settings/llm/active", headers=root, json={"provider_id": created["id"]}
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["effective"]["auth_header"] == "x-api-key"
    assert activated.json()["effective"]["auth_prefix"] == ""

    from app.agents.execution import build_llm

    llm = build_llm({}, None)
    assert llm.default_headers == {"x-api-key": "sk-secret"}


def test_models_probe_uses_configured_auth(client, login, monkeypatch):
    from app.runtime import llm_config

    root = login("root", is_superadmin=True)
    created = client.post(
        "/v1/settings/llm/providers",
        headers=root,
        json={
            **PROVIDER,
            "auth_type": "header",
            "auth_header": "x-api-key",
            "auth_prefix": "",
        },
    ).json()
    client.put("/v1/settings/llm/active", headers=root, json={"provider_id": created["id"]})

    captured: dict = {}
    real_client = httpx.AsyncClient

    def factory(**kwargs):
        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["headers"] = dict(request.headers)
            return httpx.Response(200, json={"data": [{"id": "qwen3.5-4b"}]})

        kwargs.pop("follow_redirects", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(llm_config.httpx, "AsyncClient", factory)

    response = client.post("/v1/settings/llm/models", headers=root, json={})
    assert response.status_code == 200, response.text
    assert response.json()["models"] == ["qwen3.5-4b"]
    assert captured["url"] == "http://llm.local:1234/v1/models"
    assert captured["headers"]["x-api-key"] == "sk-secret"
    assert "authorization" not in captured["headers"]
