"""Rollback: publish a new version from an existing snapshot."""

from __future__ import annotations

from tests.conftest import AUTH

AGENT = {
    "slug": "rb-agent",
    "name": "RB agent",
    "system_prompt": "v1 prompt",
    "tools": ["calculator"],
}


def _publish(client, **overrides):
    payload = {**AGENT, **overrides}
    created = client.post("/v1/agents", json=payload, headers=AUTH)
    assert created.status_code == 201, created.text
    published = client.post(
        "/v1/agents/rb-agent/publish", json={"visibility": "shared"}, headers=AUTH
    )
    assert published.status_code == 200, published.text


def test_rollback_restores_snapshot_as_new_version(client):
    _publish(client)
    edited = client.patch(
        "/v1/agents/rb-agent",
        json={"system_prompt": "v2 prompt", "tools": [], "description": "second"},
        headers=AUTH,
    )
    assert edited.status_code == 200
    assert client.post(
        "/v1/agents/rb-agent/publish", json={"visibility": "private"}, headers=AUTH
    ).json()["published_version"] == 2

    rolled = client.post("/v1/agents/rb-agent/rollback", json={"version": 1}, headers=AUTH)

    assert rolled.status_code == 200, rolled.text
    body = rolled.json()
    assert body["published_version"] == 3
    assert body["system_prompt"] == "v1 prompt"
    assert body["tools"] == ["calculator"]
    assert body["description"] == ""
    assert body["visibility"] == "private"  # не передан — остаётся прежним

    versions = client.get("/v1/agents/rb-agent/versions", headers=AUTH).json()
    assert [item["version"] for item in versions] == [3, 2, 1]
    assert versions[0]["snapshot"]["system_prompt"] == "v1 prompt"


def test_rollback_can_change_visibility(client):
    _publish(client)
    rolled = client.post(
        "/v1/agents/rb-agent/rollback",
        json={"version": 1, "visibility": "private"},
        headers=AUTH,
    )
    assert rolled.status_code == 200
    assert rolled.json()["visibility"] == "private"


def test_rollback_unknown_version_is_404(client):
    _publish(client)
    missing = client.post("/v1/agents/rb-agent/rollback", json={"version": 99}, headers=AUTH)
    assert missing.status_code == 404


def test_rollback_rejects_missing_tool(client):
    created = client.post(
        "/v1/tools",
        json={
            "slug": "gone",
            "name": "Gone",
            "method": "GET",
            "url": "https://api.test/x",
            "parameters": [],
        },
        headers=AUTH,
    )
    assert created.status_code == 201
    _publish(client, tools=["gone"])
    assert client.delete("/v1/tools/gone", headers=AUTH).status_code == 200

    rolled = client.post("/v1/agents/rb-agent/rollback", json={"version": 1}, headers=AUTH)

    assert rolled.status_code == 422
    assert "gone" in rolled.json()["detail"]


def test_rollback_requires_owner(client, login):
    _publish(client)
    stranger = login("stranger")
    denied = client.post(
        "/v1/agents/rb-agent/rollback", headers=stranger, json={"version": 1}
    )
    assert denied.status_code == 403
