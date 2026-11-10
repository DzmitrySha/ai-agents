"""Skills: skills.sh import, listing, agent snapshot wiring."""

from __future__ import annotations

from tests.conftest import AUTH

SKILL_MD = """---
name: Frontend Design
description: Guidance for distinctive interfaces
---

# Frontend Design

Use intentional spacing and typography.
"""

FILES = [
    {"path": "SKILL.md", "contents": SKILL_MD},
    {"path": "examples/example.md", "contents": "example"},
]


def _patch_github(monkeypatch):
    from app.repos import skills as repo

    async def fake_github(source: str, slug: str):
        return "Frontend Design", "Guidance for distinctive interfaces", SKILL_MD, FILES, "main"

    async def no_official(source_id: str):
        return None

    monkeypatch.setattr(repo, "_github_skill", fake_github)
    monkeypatch.setattr(repo, "_official_skill", no_official)


def test_import_skill_from_skills_sh_url(client, monkeypatch):
    _patch_github(monkeypatch)
    response = client.post(
        "/v1/skills/import",
        headers=AUTH,
        json={"url": "https://www.skills.sh/anthropics/skills/frontend-design"},
    )
    assert response.status_code == 201, response.text
    skill = response.json()
    assert skill["slug"] == "frontend-design"
    assert skill["source"] == "skills.sh"
    assert skill["source_id"] == "anthropics/skills/frontend-design"
    assert "intentional spacing" in skill["content"]
    assert {item["path"] for item in skill["files"]} == {"SKILL.md", "examples/example.md"}

    listed = client.get("/v1/skills", headers=AUTH).json()
    assert listed["total"] == 1
    assert listed["items"][0]["slug"] == "frontend-design"

    detail = client.get("/v1/skills/frontend-design", headers=AUTH).json()
    assert detail["content"].startswith("---")


def test_reimport_updates_existing_skill(client, monkeypatch):
    _patch_github(monkeypatch)
    first = client.post(
        "/v1/skills/import",
        headers=AUTH,
        json={"url": "https://skills.sh/anthropics/skills/frontend-design"},
    ).json()
    second = client.post(
        "/v1/skills/import",
        headers=AUTH,
        json={"url": "anthropics/skills/frontend-design"},
    ).json()
    assert first["id"] == second["id"]
    assert client.get("/v1/skills", headers=AUTH).json()["total"] == 1


def test_import_rejects_invalid_urls(client):
    response = client.post(
        "/v1/skills/import", headers=AUTH, json={"url": "https://example.com/a/b"}
    )
    assert response.status_code == 422
    short = client.post("/v1/skills/import", headers=AUTH, json={"url": "owner/repo"})
    assert short.status_code == 422


def test_search_without_token_is_503(client):
    response = client.get("/v1/skills/search?q=design", headers=AUTH)
    assert response.status_code == 503
    assert "SKILLS_SH_TOKEN" in response.json()["detail"]


def test_delete_skill(client, monkeypatch):
    _patch_github(monkeypatch)
    skill = client.post(
        "/v1/skills/import",
        headers=AUTH,
        json={"url": "https://skills.sh/anthropics/skills/frontend-design"},
    ).json()
    assert client.delete(f"/v1/skills/{skill['id']}", headers=AUTH).status_code == 204
    assert client.get("/v1/skills", headers=AUTH).json()["total"] == 0


def test_agent_snapshot_freezes_skills_and_prompt(client, monkeypatch, fake_graph):
    _patch_github(monkeypatch)
    fake_graph()
    skill = client.post(
        "/v1/skills/import",
        headers=AUTH,
        json={"url": "https://skills.sh/anthropics/skills/frontend-design"},
    ).json()

    unknown = client.post(
        "/v1/agents",
        json={
            "slug": "skill-agent",
            "name": "Skill agent",
            "system_prompt": "Base prompt",
            "skills": ["missing-skill"],
        },
        headers=AUTH,
    )
    assert unknown.status_code == 422

    agent = client.post(
        "/v1/agents",
        json={
            "slug": "skill-agent",
            "name": "Skill agent",
            "system_prompt": "Base prompt",
            "skills": [skill["slug"]],
        },
        headers=AUTH,
    )
    assert agent.status_code == 201, agent.text
    assert agent.json()["skills"] == ["frontend-design"]

    published = client.post(
        "/v1/agents/skill-agent/publish",
        json={"visibility": "shared"},
        headers=AUTH,
    )
    assert published.status_code == 200
    versions = client.get("/v1/agents/skill-agent/versions", headers=AUTH).json()
    snapshot = versions[0]["snapshot"]
    assert snapshot["skills"] == ["frontend-design"]
    assert snapshot["skill_defs"][0]["slug"] == "frontend-design"
    assert "intentional spacing" in snapshot["skill_defs"][0]["content"]

    run_id = client.post(
        "/v1/runs", json={"agent_id": "skill-agent", "input": "hi"}, headers=AUTH
    ).json()["run_id"]
    import time

    for _ in range(200):
        status = client.get(f"/v1/runs/{run_id}", headers=AUTH).json()["status"]
        if status in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.02)
    assert status == "succeeded"
