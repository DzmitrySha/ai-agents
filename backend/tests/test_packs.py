"""Code-registered packs: manifest validation, dry-run, idempotent install."""

from __future__ import annotations

import yaml

from app.plugins import packs as registry
from app.runtime.models import PackManifest
from tests.conftest import AUTH


def _manifest(**overrides) -> PackManifest:
    payload = {
        "name": "test-pack",
        "version": "1",
        "description": "Test pack",
        "tools": ["calculator"],
        "skills": [],
        "agents": [
            {
                "slug": "pack-agent",
                "name": "Pack agent",
                "description": "from pack",
                "system_prompt": "be brief",
                "tools": ["calculator"],
            }
        ],
    }
    payload.update(overrides)
    return PackManifest.model_validate(payload)


def _agent_count(client) -> int:
    rows = client.get("/v1/agents?limit=100", headers=AUTH).json()["items"]
    return len([row for row in rows if row["slug"] == "pack-agent"])


def test_dry_run_then_install_is_idempotent(client, login, monkeypatch):
    monkeypatch.setitem(registry.PACKS, "test-pack", _manifest())
    headers = login("root", is_superadmin=True)

    listed = client.get("/v1/packs", headers=headers)
    assert listed.status_code == 200
    item = next(row for row in listed.json() if row["name"] == "test-pack")
    assert item["agents"] == ["pack-agent"]
    assert item["installed_versions"] == []

    dry = client.post("/v1/packs/test-pack/install?dry_run=true", headers=headers)
    assert dry.status_code == 200, dry.text
    assert dry.json()["dry_run"] is True
    assert dry.json()["changes"] == [
        {"entity": "agent", "ref": "pack-agent", "action": "create"}
    ]
    assert _agent_count(client) == 0

    installed = client.post("/v1/packs/test-pack/install", headers=headers)
    assert installed.status_code == 200, installed.text
    assert installed.json()["installed"] is True
    assert installed.json()["changes"][0]["action"] == "create"

    agent = client.get("/v1/agents/pack-agent", headers=AUTH).json()
    assert agent["status"] == "published"
    assert agent["visibility"] == "shared"
    assert agent["published_version"] == 1

    replay = client.post("/v1/packs/test-pack/install", headers=headers)
    assert replay.status_code == 200
    assert replay.json()["already_installed"] is True
    assert replay.json()["changes"] == []
    assert _agent_count(client) == 1

    listed = client.get("/v1/packs", headers=headers).json()
    item = next(row for row in listed if row["name"] == "test-pack")
    assert item["installed_versions"] == ["1"]


def test_new_version_updates_pack_agent(client, login, monkeypatch):
    monkeypatch.setitem(registry.PACKS, "test-pack", _manifest())
    headers = login("root", is_superadmin=True)
    assert client.post("/v1/packs/test-pack/install", headers=headers).status_code == 200

    monkeypatch.setitem(
        registry.PACKS,
        "test-pack",
        _manifest(version="2", agents=[
            {
                "slug": "pack-agent",
                "name": "Pack agent v2",
                "description": "updated",
                "system_prompt": "be even briefer",
                "tools": ["calculator"],
            }
        ]),
    )
    dry = client.post("/v1/packs/test-pack/install?dry_run=true", headers=headers)
    assert dry.json()["changes"][0]["action"] == "update"
    installed = client.post("/v1/packs/test-pack/install", headers=headers)
    assert installed.status_code == 200
    assert installed.json()["installed"] is True

    agent = client.get("/v1/agents/pack-agent", headers=AUTH).json()
    assert agent["name"] == "Pack agent v2"
    assert agent["published_version"] == 2


def test_missing_ref_is_409_and_writes_nothing(client, login, monkeypatch):
    monkeypatch.setitem(
        registry.PACKS,
        "test-pack",
        _manifest(skills=["missing-skill"]),
    )
    headers = login("root", is_superadmin=True)
    response = client.post("/v1/packs/test-pack/install", headers=headers)
    assert response.status_code == 409
    assert "missing-skill" in response.json()["detail"]
    assert _agent_count(client) == 0


def test_existing_user_agent_conflicts(client, login, monkeypatch):
    created = client.post(
        "/v1/agents",
        json={
            "slug": "pack-agent",
            "name": "User agent",
            "system_prompt": "mine",
        },
        headers=AUTH,
    )
    assert created.status_code == 201
    monkeypatch.setitem(registry.PACKS, "test-pack", _manifest())
    headers = login("root", is_superadmin=True)
    response = client.post("/v1/packs/test-pack/install", headers=headers)
    assert response.status_code == 409
    assert "outside pack" in response.json()["detail"]


def test_custom_pack_can_be_created_updated_and_deleted(client, login):
    headers = login("root", is_superadmin=True)
    manifest = _manifest()
    created = client.post(
        "/v1/packs", json=manifest.model_dump(mode="json"), headers=headers
    )
    assert created.status_code == 201, created.text
    assert created.json()["source"] == "custom"

    listed = client.get("/v1/packs", headers=headers).json()
    item = next(row for row in listed if row["name"] == "test-pack")
    assert item["source"] == "custom"

    updated = client.put(
        "/v1/packs/test-pack",
        json=_manifest(version="2").model_dump(mode="json"),
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == "2"

    installed = client.post("/v1/packs/test-pack/install", headers=headers)
    assert installed.status_code == 200
    assert installed.json()["installed"] is True

    deleted = client.delete("/v1/packs/test-pack", headers=headers)
    assert deleted.status_code == 204
    assert all(
        row["name"] != "test-pack" for row in client.get("/v1/packs", headers=headers).json()
    )


def test_code_pack_is_immutable(client, login):
    headers = login("root", is_superadmin=True)
    response = client.post(
        "/v1/packs",
        json=_manifest(name="starter").model_dump(mode="json"),
        headers=headers,
    )
    assert response.status_code == 409
    assert client.delete("/v1/packs/starter", headers=headers).status_code == 409


def test_requires_superadmin(client, login, monkeypatch):
    monkeypatch.setitem(registry.PACKS, "test-pack", _manifest())
    headers = login("plain", is_superadmin=False)
    assert client.get("/v1/packs", headers=headers).status_code == 403


def test_yaml_manifest_loader(tmp_path):
    (tmp_path / "demo.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "yaml-pack",
                "version": "1.2.0",
                "tools": [],
                "skills": [],
                "agents": [
                    {
                        "slug": "yaml-agent",
                        "name": "YAML",
                        "system_prompt": "hi",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    loaded = registry.load_packs(tmp_path)
    assert loaded["yaml-pack"].version == "1.2.0"
