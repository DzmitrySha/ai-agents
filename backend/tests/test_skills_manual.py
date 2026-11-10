"""Manual skills (skills.sh template) and AI generation of SKILL.md."""

from __future__ import annotations

from tests.conftest import AUTH

CONTENT = """---
name: code-review
description: Проверка пул-реквестов по чек-листу
---

# Проверка кода

## Когда использовать
Когда пользователь просит ревью изменений.
"""


def test_create_manual_skill_and_duplicate(client):
    created = client.post(
        "/v1/skills",
        json={
            "name": "Проверка кода",
            "slug": "code-review",
            "description": "Чек-лист ревью",
            "content": CONTENT,
        },
        headers=AUTH,
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["source"] == "manual"
    assert body["slug"] == "code-review"
    assert body["content"].startswith("---")

    duplicate = client.post(
        "/v1/skills",
        json={"name": "Another", "slug": "code-review", "content": "x"},
        headers=AUTH,
    )
    assert duplicate.status_code == 409


def test_slug_is_transliterated_when_omitted(client):
    created = client.post(
        "/v1/skills",
        json={"name": "Проверка кода", "content": CONTENT},
        headers=AUTH,
    )

    assert created.status_code == 201, created.text
    assert created.json()["slug"] == "proverka-koda"


def test_update_manual_skill(client):
    created = client.post(
        "/v1/skills",
        json={"name": "Code review", "slug": "code-review", "content": CONTENT},
        headers=AUTH,
    ).json()

    patched = client.patch(
        f"/v1/skills/{created['slug']}",
        json={"description": "новое описание", "content": CONTENT + "\nДополнение."},
        headers=AUTH,
    )

    assert patched.status_code == 200, patched.text
    assert patched.json()["description"] == "новое описание"
    assert patched.json()["content"].endswith("Дополнение.")


def test_imported_skill_is_read_only(client, run_db):
    async def _seed():
        from app.db import get_session_factory
        from app.models import Skill

        async with get_session_factory()() as session:
            session.add(
                Skill(
                    slug="imported",
                    name="Imported",
                    description="",
                    source="skills.sh",
                    source_id="owner/repo/skill",
                    content="---\nname: imported\n---\n",
                    files=[],
                    created_by="",
                )
            )
            await session.commit()

    run_db(_seed)

    response = client.patch(
        "/v1/skills/imported", json={"description": "hack"}, headers=AUTH
    )
    assert response.status_code == 409
    assert "импортирован" in response.json()["detail"]


def test_assist_skill_normalizes_content(client, monkeypatch):
    from app.routers import assist as assist_module

    async def fake_complete(system: str, user: str, llm=None):
        return {
            "name": "Проверка релиза",
            "slug": "Release Check!",
            "description": "Чек-лист перед релизом",
            "content": "```markdown\n# Чек-лист\n\n1. Собрать образ\n```",
            "notes": "Уточните список окружений",
        }

    monkeypatch.setattr(assist_module, "complete_json", fake_complete)

    response = client.post(
        "/v1/assist/skill",
        headers=AUTH,
        json={"description": "навык проверки релиза"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["slug"] == "release-check"
    assert body["content"].startswith("---\nname: Проверка релиза")
    assert "Собрать образ" in body["content"]
    assert any("frontmatter" in warning for warning in body["warnings"])
    assert body["notes"] == "Уточните список окружений"


def test_assist_skill_avoids_taken_slug(client, monkeypatch):
    from app.routers import assist as assist_module

    client.post(
        "/v1/skills",
        json={"name": "Taken", "slug": "taken-slug", "content": CONTENT},
        headers=AUTH,
    )

    async def fake_complete(system: str, user: str, llm=None):
        return {"name": "Taken", "slug": "taken-slug", "content": CONTENT}

    monkeypatch.setattr(assist_module, "complete_json", fake_complete)

    body = client.post(
        "/v1/assist/skill", headers=AUTH, json={"description": "дубль"}
    ).json()

    assert body["slug"] == "taken-slug-2"


def test_assist_skill_keeps_single_frontmatter(client, monkeypatch):
    from app.routers import assist as assist_module

    async def fake_complete(system: str, user: str, llm=None):
        return {
            "name": "Дубликат",
            "slug": "dup-fm",
            "description": "Проверка",
            # модель вернула frontmatter дважды, с ведущими пробелами
            "content": "  \n---\nname: one\ndescription: one\n---\n"
            "\n---\nname: two\ndescription: two\n---\n\n# Тело\n",
        }

    monkeypatch.setattr(assist_module, "complete_json", fake_complete)

    content = client.post(
        "/v1/assist/skill", headers=AUTH, json={"description": "дубль frontmatter"}
    ).json()["content"]

    assert content.count("name:") == 1
    assert content.startswith("---\nname: Дубликат")
    assert content.endswith("# Тело")
