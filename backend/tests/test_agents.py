"""Agents: visibility, ownership, publish/versions, clone."""

from __future__ import annotations

from tests.conftest import AUTH

BASE = {
    "slug": "alpha",
    "name": "Alpha",
    "description": "",
    "kind": "preset",
    "system_prompt": "Ты тестовый агент.",
    "tools": ["calculator"],
    "llm": {"temperature": 0.1},
    "limits": {"max_steps": 4, "timeout_seconds": 30},
}


def _create(client, headers, **overrides):
    response = client.post("/v1/agents", json={**BASE, **overrides}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_preset_is_private_draft(client):
    agent = _create(client, AUTH)
    assert agent["status"] == "draft"
    assert agent["visibility"] == "private"
    assert agent["published_version"] is None
    assert agent["owner"]["kind"] == "service"
    assert agent["limits"] == {"max_steps": 4, "timeout_seconds": 30}


def test_duplicate_slug_is_409(client):
    _create(client, AUTH)
    response = client.post("/v1/agents", json=BASE, headers=AUTH)
    assert response.status_code == 409


def test_publish_creates_versions(client):
    agent = _create(client, AUTH)
    published = client.post(
        f"/v1/agents/{agent['slug']}/publish",
        json={"visibility": "shared"},
        headers=AUTH,
    )
    assert published.status_code == 200
    assert published.json()["published_version"] == 1
    assert published.json()["visibility"] == "shared"

    patched = client.patch(
        f"/v1/agents/{agent['slug']}",
        json={"name": "Alpha v2", "limits": {"max_steps": 5, "timeout_seconds": 30}},
        headers=AUTH,
    )
    assert patched.status_code == 200
    again = client.post(
        f"/v1/agents/{agent['slug']}/publish",
        json={"visibility": "shared"},
        headers=AUTH,
    ).json()
    assert again["published_version"] == 2

    versions = client.get(f"/v1/agents/{agent['slug']}/versions", headers=AUTH).json()
    assert [item["version"] for item in versions] == [2, 1]
    assert versions[0]["snapshot"]["name"] == "Alpha v2"
    assert versions[1]["snapshot"]["name"] == "Alpha"


def test_slug_is_immutable(client):
    agent = _create(client, AUTH)
    response = client.patch(
        f"/v1/agents/{agent['slug']}", json={"slug": "beta"}, headers=AUTH
    )
    assert response.status_code == 422


def test_user_isolation_and_shared_visibility(client, login):
    _create(client, AUTH)  # service-owned private draft
    owner_headers = login("user-a")
    agent = _create(client, owner_headers, slug="user-a-agent", name="A only")
    assert agent["owner"] == {"kind": "user", "id": "user-a", "email": "user-a@example.test"}
    foreign_headers = login("user-b")

    assert client.get("/v1/agents/user-a-agent", headers=foreign_headers).status_code == 404
    assert client.patch(
        "/v1/agents/user-a-agent",
        json={"name": "hijack"},
        headers=foreign_headers,
    ).status_code == 403
    owned = client.get("/v1/agents?scope=owned", headers=foreign_headers).json()
    assert owned["total"] == 0

    owner_headers = login("user-a")
    published = client.post(
        "/v1/agents/user-a-agent/publish",
        json={"visibility": "shared"},
        headers=owner_headers,
    )
    assert published.status_code == 200, published.text

    foreign_headers = login("user-b")
    shared = client.get("/v1/agents?scope=shared", headers=foreign_headers).json()
    slugs = {item["slug"] for item in shared["items"]}
    assert slugs == {"user-a-agent"}
    assert client.get("/v1/agents/user-a-agent", headers=foreign_headers).status_code == 200

    owner_headers = login("user-a")
    own_scope = client.get("/v1/agents?scope=owned", headers=owner_headers).json()
    assert {item["slug"] for item in own_scope["items"]} == {"user-a-agent"}
    # Владелец тоже видит свой published+shared в scope=shared (MCP allowlist / «Общие»).
    owner_shared = client.get("/v1/agents?scope=shared", headers=owner_headers).json()
    assert "user-a-agent" in {item["slug"] for item in owner_shared["items"]}


def test_service_scope_shared_excludes_own_drafts(client):
    _create(client, AUTH, slug="svc-draft")
    shared = client.get("/v1/agents?scope=shared", headers=AUTH).json()
    assert all(item["status"] == "published" for item in shared["items"])
    owned = client.get("/v1/agents?scope=owned", headers=AUTH).json()
    assert "svc-draft" in {item["slug"] for item in owned["items"]}


def test_scope_all_is_superadmin_only(client, login):
    user_headers = login("user-a")
    _create(client, user_headers, slug="hidden")
    assert client.get("/v1/agents?scope=all", headers=user_headers).status_code == 403

    admin_headers = login("root", is_superadmin=True)
    all_agents = client.get("/v1/agents?scope=all", headers=admin_headers).json()
    assert "hidden" in {item["slug"] for item in all_agents["items"]}


def test_clone_creates_private_copy(client, login):
    owner_headers = login("user-a")
    _create(client, owner_headers, slug="source")
    client.post(
        "/v1/agents/source/publish",
        json={"visibility": "shared"},
        headers=owner_headers,
    )

    copier_headers = login("user-b")
    clone = client.post("/v1/agents/source/clone", headers=copier_headers)
    assert clone.status_code == 201
    body = clone.json()
    assert body["slug"].startswith("source-copy-")
    assert body["owner"]["id"] == "user-b"
    assert body["status"] == "draft"
    assert body["visibility"] == "private"
    assert body["published_version"] is None


def test_tools_are_validated(client):
    response = client.post(
        "/v1/agents",
        json={**BASE, "slug": "bad-tool", "tools": ["nope"]},
        headers=AUTH,
    )
    assert response.status_code == 422


def test_llm_api_key_is_rejected(client):
    response = client.post(
        "/v1/agents",
        json={**BASE, "slug": "leaky", "llm": {"api_key": "secret"}},
        headers=AUTH,
    )
    assert response.status_code == 422


def test_plugin_requires_name_and_publishes(client):
    missing = client.post(
        "/v1/agents",
        json={**BASE, "slug": "plug", "kind": "plugin", "system_prompt": ""},
        headers=AUTH,
    )
    assert missing.status_code == 422

    plugin = _create(
        client,
        AUTH,
        slug="plug",
        kind="plugin",
        plugin_name="echo",
        system_prompt="",
        tools=[],
    )
    assert plugin["status"] == "published"
    assert plugin["published_version"] == 1


def test_archive_hides_from_default_list(client):
    _create(client, AUTH, slug="archivable")
    response = client.delete("/v1/agents/archivable", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["status"] == "archived"
    shared = client.get("/v1/agents?scope=shared", headers=AUTH).json()
    assert "archivable" not in {item["slug"] for item in shared["items"]}
    owned = client.get("/v1/agents?scope=owned", headers=AUTH).json()
    assert "archivable" not in {item["slug"] for item in owned["items"]}
    archived = client.get("/v1/agents?scope=archived", headers=AUTH).json()
    assert "archivable" in {item["slug"] for item in archived["items"]}
    assert client.get("/v1/agents/archivable", headers=AUTH).status_code == 200


def test_purge_archived_agent(client):
    _create(client, AUTH, slug="purge-me")
    assert client.delete("/v1/agents/purge-me", headers=AUTH).status_code == 200
    purged = client.delete("/v1/agents/purge-me", headers=AUTH)
    assert purged.status_code == 204
    assert client.get("/v1/agents/purge-me", headers=AUTH).status_code == 404
    assert "purge-me" not in {
        item["slug"]
        for item in client.get("/v1/agents?scope=archived", headers=AUTH).json()["items"]
    }
