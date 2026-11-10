"""LLM autofill (`/v1/assist/*`): catalogue filtering and normalization."""

from __future__ import annotations

import pytest

from tests.conftest import AUTH


def _mock_llm(monkeypatch, payload):
    """Patch the single LLM call the router makes."""
    from app.routers import assist as router_module

    async def fake(system: str, user: str, llm=None):
        if isinstance(payload, Exception):
            raise payload
        return payload

    monkeypatch.setattr(router_module, "complete_json", fake)


def _seed_skill(
    run_db,
    *,
    slug: str = "frontend-design",
    name: str = "Frontend design",
    description: str = "Layout rules",
) -> None:
    async def _insert() -> None:
        from app.db import get_session_factory
        from app.models import Skill

        async with get_session_factory()() as session:
            session.add(Skill(slug=slug, name=name, description=description))
            await session.commit()

    run_db(_insert)


def test_agent_suggestion_keeps_only_real_tools_and_skills(client, run_db, monkeypatch):
    _seed_skill(run_db)
    _mock_llm(
        monkeypatch,
        {
            "name": "Помощник по расчётам",
            "slug": "calc-helper",
            "description": "Считает выражения и подсказывает время.",
            "system_prompt": "Ты помогаешь считать выражения.",
            "tools": ["calculator", "made-up-tool", "calculator"],
            "skills": ["frontend-design", "missing-skill"],
            "new_tools": [
                {
                    "slug": "weather",
                    "name": "Погода",
                    "description": "Прогноз по городу",
                    "note": "https://api.test/weather",
                },
                {"slug": "calculator", "name": "Дубль", "description": "", "note": ""},
            ],
            "notes": "Уточните город.",
        },
    )

    response = client.post(
        "/v1/assist/agent", headers=AUTH, json={"description": "Агент-калькулятор"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tools"] == ["calculator"]
    assert body["skills"] == ["frontend-design"]
    assert [tool["slug"] for tool in body["new_tools"]] == ["weather"]
    assert body["notes"] == "Уточните город."
    assert any("made-up-tool" in warning for warning in body["warnings"])
    assert any("missing-skill" in warning for warning in body["warnings"])


def test_agent_suggestion_avoids_taken_slug(client, monkeypatch):
    created = client.post(
        "/v1/agents",
        headers=AUTH,
        json={"slug": "calc-helper", "name": "Existing", "system_prompt": "p"},
    )
    assert created.status_code == 201
    _mock_llm(
        monkeypatch,
        {"name": "Дубль", "slug": "calc-helper", "system_prompt": "p"},
    )

    body = client.post(
        "/v1/assist/agent", headers=AUTH, json={"description": "Ещё один калькулятор"}
    ).json()

    assert body["slug"] == "calc-helper-2"
    assert any("занят" in warning for warning in body["warnings"])


def test_tool_suggestion_normalizes_model_output(client, monkeypatch):
    _mock_llm(
        monkeypatch,
        {
            "slug": "Погода сегодня",
            "name": "Погода",
            "description": "Прогноз по городу",
            "method": "fetch",
            "url": "api.test/weather",
            "headers": {"X-Key": None},
            "query": {"q": "{city}"},
            "body_template": "",
            "content_type": "application/json",
            "parameters": [
                {"name": "city", "type": "text", "required": True},
                {"name": "1bad", "type": "string"},
            ],
            "notes": "",
        },
    )

    body = client.post(
        "/v1/assist/tool", headers=AUTH, json={"description": "Инструмент погоды"}
    ).json()

    assert body["slug"] == "pogoda-segodnya"
    assert body["method"] == "GET"
    assert body["url"] == ""
    assert body["headers"] == {"X-Key": ""}
    assert body["query"] == {"q": "{city}"}
    assert [param["name"] for param in body["parameters"]] == ["city"]
    assert body["parameters"][0]["type"] == "string"
    assert body["notes"]
    assert any("fetch" in warning.lower() for warning in body["warnings"])
    assert any("1bad" in warning for warning in body["warnings"])


def test_llm_failure_is_502(client, monkeypatch):
    from app.agents.assist import AssistError

    _mock_llm(monkeypatch, AssistError("LLM недоступен: timeout"))

    response = client.post(
        "/v1/assist/agent", headers=AUTH, json={"description": "любой агент"}
    )

    assert response.status_code == 502
    assert "LLM недоступен" in response.json()["detail"]


def test_requires_agents_write_scope(client, login):
    admin_headers = login("root", is_superadmin=True)
    created = client.post(
        "/api/admin/service-keys",
        headers=admin_headers,
        json={"name": "reader", "scopes": ["runs:read"]},
    ).json()
    bearer = {"Authorization": f"Bearer {created['key']}"}

    assert (
        client.post(
            "/v1/assist/agent", headers=bearer, json={"description": "агент"}
        ).status_code
        == 403
    )
    client.cookies.clear()
    assert (
        client.post("/v1/assist/tool", json={"description": "инструмент"}).status_code
        == 401
    )


def test_parse_json_object_strips_code_fence():
    from app.agents.assist import AssistError, parse_json_object

    assert parse_json_object('```json\n{"name": "x"}\n```') == {"name": "x"}
    assert parse_json_object('Вот результат: {"a": 1} — готово') == {"a": 1}
    with pytest.raises(AssistError):
        parse_json_object("JSON нет вовсе")


def test_complete_json_retries_with_correction(monkeypatch):
    """Первый ответ — проза, второй — JSON: подсказчик всё равно возвращает объект."""
    from types import SimpleNamespace

    from app.agents import assist

    answers = ["Конечно! Вот инструмент:", '{"slug": "weather"}']
    calls: list[list] = []

    class _FakeModel:
        async def ainvoke(self, messages):
            calls.append(messages)
            return SimpleNamespace(content=answers[len(calls) - 1])

    monkeypatch.setattr(assist, "build_model", lambda llm=None: _FakeModel())

    import asyncio

    result = asyncio.run(assist.complete_json("sys", "user"))

    assert result == {"slug": "weather"}
    assert len(calls) == 2
    assert "ТОЛЬКО JSON" in calls[1][-1].content


def test_complete_json_reports_raw_answer(monkeypatch):
    from types import SimpleNamespace

    from app.agents import assist

    class _FakeModel:
        async def ainvoke(self, messages):
            return SimpleNamespace(content="не могу помочь")

    monkeypatch.setattr(assist, "build_model", lambda llm=None: _FakeModel())

    import asyncio

    with pytest.raises(assist.AssistError) as excinfo:
        asyncio.run(assist.complete_json("sys", "user"))

    assert "не могу помочь" in str(excinfo.value)


def test_chat_form_mode_returns_clean_fields(client, monkeypatch):
    from app.routers import assist as router_module

    captured: dict = {}

    async def fake(system: str, user: str, llm=None):
        captured["system"] = system
        captured["user"] = user
        return {
            "answer": "Собрал агента-калькулятор",
            "fields": {
                "name": "Калькулятор",
                "slug": "calc",
                "system_prompt": "Считай выражения калькулятором.",
                "tools": ["calculator"],
                "limits": {"max_steps": 4},
                "api_key": "SECRET",  # не поле формы — отбрасывается
            },
            "warnings": ["Проверьте лимит шагов"],
        }

    from app.agents import assist as assist_module

    monkeypatch.setattr(assist_module, "complete_json", fake)

    response = client.post(
        "/v1/assist/chat",
        headers=AUTH,
        json={
            "mode": "form",
            "target": "agent",
            "message": "сделай агента калькулятора",
            "current": {"name": "старое"},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer"].startswith("Собрал")
    assert body["fields"] == {
        "name": "Калькулятор",
        "slug": "calc",
        "system_prompt": "Считай выражения калькулятором.",
        "tools": ["calculator"],
        "limits": {"max_steps": 4},
    }
    assert body["warnings"] == ["Проверьте лимит шагов"]
    # в промпт попали каталог инструментов и текущие значения формы
    assert "calculator" in captured["user"]
    assert "старое" in captured["user"]


def test_chat_advice_mode_has_no_fields(client, monkeypatch):
    async def fake(system: str, user: str, llm=None):
        return {"answer": "Откройте /mcp и создайте ключ.", "fields": {"name": "x"}}

    from app.agents import assist as assist_module

    monkeypatch.setattr(assist_module, "complete_json", fake)

    body = client.post(
        "/v1/assist/chat",
        headers=AUTH,
        json={"mode": "advice", "target": "general", "message": "как выдать MCP-ключ?"},
    ).json()
    assert body["fields"] is None
    assert "/mcp" in body["answer"]


def test_chat_context_includes_skill_descriptions(client, run_db, monkeypatch):
    """Каталог в advice должен содержать slug + описание — иначе «найди навык про git» слеп."""
    _seed_skill(
        run_db,
        slug="uc-git-ops",
        name="Git ops",
        description="Performs git operations: branches, commits, push, merge",
    )
    captured: dict = {}

    async def fake(system: str, user: str, llm=None):
        captured["system"] = system
        captured["user"] = user
        return {
            "answer": "Подойдёт uc-git-ops — git-операции по правилам репозитория.",
            "fields": None,
            "warnings": [],
        }

    from app.agents import assist as assist_module

    monkeypatch.setattr(assist_module, "complete_json", fake)

    response = client.post(
        "/v1/assist/chat",
        headers=AUTH,
        json={
            "mode": "advice",
            "target": "skill",
            "message": "найди все навыки на этой странице для работы с гит",
        },
    )
    assert response.status_code == 200, response.text
    assert "uc-git-ops" in captured["user"]
    assert "git operations" in captured["user"].lower() or "Performs git" in captured["user"]
    assert "Установленные навыки" in captured["user"]
    assert "find-skills" in captured["system"] or "каталог" in captured["system"].lower()


def test_chat_form_mcp_server_keeps_allowlist_slugs(client, monkeypatch):
    async def fake(system: str, user: str, llm=None):
        return {
            "answer": "Сервер для Cursor",
            "fields": {
                "slug": "cursor",
                "name": "Cursor",
                "description": "IDE",
                "agent_slugs": ["demo-chat"],
                "tool_slugs": [],
                "skill_slugs": ["uc-git-ops"],
            },
            "warnings": [],
        }

    from app.agents import assist as assist_module

    monkeypatch.setattr(assist_module, "complete_json", fake)

    body = client.post(
        "/v1/assist/chat",
        headers=AUTH,
        json={
            "mode": "form",
            "target": "mcp-server",
            "message": "ключ для Cursor с demo-chat",
            "current": {},
        },
    ).json()
    assert body["fields"]["agent_slugs"] == ["demo-chat"]
    assert body["fields"]["skill_slugs"] == ["uc-git-ops"]


def test_chat_form_requires_write_scope(client, login, monkeypatch):
    from app.routers import assist as router_module

    async def fake(system: str, user: str, llm=None):
        return {"answer": "ok", "fields": {"name": "x"}}

    from app.agents import assist as assist_module

    monkeypatch.setattr(assist_module, "complete_json", fake)

    viewer = login("viewer", app_role="user")
    blocked = client.post(
        "/v1/assist/chat",
        headers=viewer,
        json={"mode": "form", "target": "agent", "message": "заполни"},
    )
    assert blocked.status_code == 403, blocked.text

    allowed = client.post(
        "/v1/assist/chat",
        headers=viewer,
        json={"mode": "advice", "target": "general", "message": "как?"},
    )
    assert allowed.status_code == 200, allowed.text


def test_chat_service_keys_target_accepts_page_search(client, monkeypatch):
    async def fake(system: str, user: str, llm=None):
        return {"answer": "ищем ключ", "fields": {"page_search": "factory"}, "warnings": []}

    from app.agents import assist as assist_module

    monkeypatch.setattr(assist_module, "complete_json", fake)

    body = client.post(
        "/v1/assist/chat",
        headers=AUTH,
        json={
            "mode": "form",
            "target": "service-keys",
            "message": "найди ключ factory",
            "current": {},
        },
    ).json()
    assert body["fields"] == {"page_search": "factory"}
