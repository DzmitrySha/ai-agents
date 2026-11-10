"""Hybrid catalog + tool invoke + service-key allowlists."""

from __future__ import annotations

from tests.conftest import AUTH


def _create_db_service_key(client, headers, **extra):
    body = {
        "name": extra.pop("name", "factory"),
        "scopes": extra.pop(
            "scopes",
            [
                "agents:read",
                "tools:read",
                "tools:execute",
                "skills:read",
                "runs:read",
                "runs:execute",
            ],
        ),
        **extra,
    }
    response = client.post("/api/admin/service-keys", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_catalog_env_key_unrestricted(client, login):
    admin = login("root", is_superadmin=True)
    created = client.post(
        "/v1/skills",
        headers=admin,
        json={
            "name": "Brief",
            "slug": "brief-reply",
            "description": "short",
            "content": "# Brief\n",
        },
    )
    assert created.status_code == 201, created.text
    catalog = client.get("/v1/catalog", headers=AUTH)
    assert catalog.status_code == 200, catalog.text
    body = catalog.json()
    assert any(tool["name"] == "calculator" for tool in body["tools"])
    assert any(skill["slug"] == "brief-reply" for skill in body["skills"])


def test_catalog_and_invoke_respect_service_allowlist(client, login):
    admin = login("root", is_superadmin=True)
    skill = client.post(
        "/v1/skills",
        headers=admin,
        json={
            "name": "Brief",
            "slug": "brief-reply",
            "description": "short",
            "content": "# Brief\nBe short.\n",
        },
    )
    assert skill.status_code == 201, skill.text

    created = _create_db_service_key(
        client,
        admin,
        tool_slugs=["calculator"],
        skill_slugs=["brief-reply"],
        agent_slugs=[],
    )
    headers = {"Authorization": f"Bearer {created['key']}"}

    emptyish = _create_db_service_key(
        client, admin, name="deny", tool_slugs=[], skill_slugs=[], agent_slugs=[]
    )
    deny_headers = {"Authorization": f"Bearer {emptyish['key']}"}

    catalog = client.get("/v1/catalog", headers=headers)
    assert catalog.status_code == 200
    body = catalog.json()
    assert body["agents"] == []
    assert [tool["name"] for tool in body["tools"]] == ["calculator"]
    assert [skill["slug"] for skill in body["skills"]] == ["brief-reply"]

    denied = client.get("/v1/catalog", headers=deny_headers)
    assert denied.status_code == 200
    assert denied.json() == {"agents": [], "tools": [], "skills": []}

    ok = client.post(
        "/v1/tools/calculator/invoke",
        headers=headers,
        json={"params": {"expression": "2+2"}},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["ok"] is True
    assert ok.json()["output"] == "4"

    blocked = client.post(
        "/v1/tools/now/invoke",
        headers=headers,
        json={"params": {}},
    )
    assert blocked.status_code == 404

    skill_ok = client.get("/v1/skills/brief-reply", headers=headers)
    assert skill_ok.status_code == 200
    assert "Be short" in skill_ok.json()["content"]

    skill_denied = client.get("/v1/skills/brief-reply", headers=deny_headers)
    assert skill_denied.status_code == 404
