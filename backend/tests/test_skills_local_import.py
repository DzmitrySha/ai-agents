"""Local skill import: server path under STORAGE_PATH and browser entries."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import AUTH

SKILL_MD = """---
name: local-review
description: Локальный навык ревью
---

# Review

## Когда использовать
Всегда при ревью.
"""


def test_import_local_file_and_folder(client, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    from app.settings import get_settings

    get_settings.cache_clear()

    single = tmp_path / "solo.md"
    single.write_text(SKILL_MD, encoding="utf-8")

    folder = tmp_path / "pack"
    skill_dir = folder / "pr-checklist"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(SKILL_MD.replace("local-review", "pr-checklist"), encoding="utf-8")
    (skill_dir / "notes.md").write_text("# notes\n", encoding="utf-8")

    file_resp = client.post(
        "/v1/skills/import-local",
        json={"path": str(single)},
        headers=AUTH,
    )
    assert file_resp.status_code == 201, file_resp.text
    body = file_resp.json()
    assert body["created"] == 1
    assert body["items"][0]["source"] == "local"
    assert body["items"][0]["name"] == "local-review"

    folder_resp = client.post(
        "/v1/skills/import-local",
        json={"path": str(folder)},
        headers=AUTH,
    )
    assert folder_resp.status_code == 201, folder_resp.text
    folder_body = folder_resp.json()
    assert folder_body["created"] == 1
    assert folder_body["items"][0]["slug"].startswith("pr-checklist") or folder_body["items"][0]["name"] == "pr-checklist"

    # Re-import updates, does not duplicate by source_id.
    again = client.post(
        "/v1/skills/import-local",
        json={"path": str(folder)},
        headers=AUTH,
    )
    assert again.status_code == 201, again.text
    assert again.json()["updated"] == 1
    assert again.json()["created"] == 0

    get_settings.cache_clear()


def test_import_local_entries_from_browser(client):
    response = client.post(
        "/v1/skills/import-local",
        json={
            "entries": [
                {
                    "path": "cursor-skill/SKILL.md",
                    "content": SKILL_MD.replace("local-review", "cursor-skill"),
                },
                {"path": "cursor-skill/extra.md", "content": "extra"},
            ]
        },
        headers=AUTH,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] == 1
    assert body["items"][0]["source"] == "local"
    detail = client.get(f"/v1/skills/{body['items'][0]['slug']}", headers=AUTH)
    assert detail.status_code == 200
    files = detail.json()["files"]
    extra = next(f for f in files if f["path"] == "extra.md")
    assert extra.get("contents") == "extra"
    assert "content" not in extra or extra.get("contents") == "extra"


def test_import_local_path_outside_roots_rejected(client, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path / "allowed"))
    (tmp_path / "allowed").mkdir()
    outside = tmp_path / "secret.md"
    outside.write_text(SKILL_MD, encoding="utf-8")

    from app.settings import get_settings

    get_settings.cache_clear()
    try:
        response = client.post(
            "/v1/skills/import-local",
            json={"path": str(outside)},
            headers=AUTH,
        )
        assert response.status_code == 422
        assert "outside" in response.text.lower() or "roots" in response.text.lower()
    finally:
        get_settings.cache_clear()


def test_import_local_requires_path_or_entries(client):
    response = client.post("/v1/skills/import-local", json={}, headers=AUTH)
    assert response.status_code == 422
