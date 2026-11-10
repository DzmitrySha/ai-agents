"""LLM-assisted autofill for agent/tool forms.

Pure suggestion layer: nothing is persisted, no secrets are generated.
The router passes the catalogue of available tools/skills plus the user's
free-form description; the model must answer with a single JSON object that
is then normalized against the real catalogue before it reaches the UI.
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.logging_setup import logger
from app.runtime.llm_config import auth_headers, project_llm
from app.runtime.models import SLUG_RE, LLMConfig
from app.runtime.slugs import slugify, unique_slug

ASSIST_TEMPERATURE = 0.1
ASSIST_TIMEOUT_SECONDS = 120.0
MAX_CONTEXT_ITEMS = 60
MAX_CONTEXT_CHARS = 160
TOOL_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
TOOL_TYPES = frozenset({"string", "number", "integer", "boolean"})
PARAM_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,40}$")



class AssistError(RuntimeError):
    """The LLM is unreachable or its answer cannot be used (router → 502)."""


AGENT_SYSTEM = """Ты — конфигуратор агентов платформы ai-agents.
Агент — это LangGraph ReAct-исполнитель с системным промптом, набором инструментов (tools) и скиллов (skills).
По словесному описанию пользователя собери его конфигурацию.

Отвечай ОДНИМ JSON-объектом, без markdown и без пояснений, ровно с ключами:
{"name": "...", "slug": "...", "description": "...", "system_prompt": "...",
 "tools": ["..."], "skills": ["..."],
 "new_tools": [{"slug": "...", "name": "...", "description": "...", "note": "..."}],
 "notes": "..."}

Правила:
- name — короткое название по-русски, до 80 символов.
- slug — только латиница/цифры/дефис, шаблон ^[a-z0-9][a-z0-9-]{1,62}$; не повторяй занятые slug агентов.
- description — 1–2 предложения по-русски.
- system_prompt — готовый системный промпт по-русски: роль, задача, границы, стиль, когда вызывать какие инструменты, требования к формату ответа. Без секретов, без выдуманных возможностей.
- tools — ТОЛЬКО имена из списка доступных инструментов (максимум 5, можно пусто).
- skills — ТОЛЬКО slug'и из списка доступных скиллов (максимум 5, можно пусто).
- new_tools — до 3 инструментов, которых не хватает: slug, name, description (что делает) и note (какой HTTP API/URL логично подключить). Не дублируй доступные.
- notes — одна фраза: что пользователю уточнить или заполнить вручную (иначе пустая строка)."""


TOOL_SYSTEM = """Ты — конструктор no-code HTTP-инструментов платформы ai-agents.
Инструмент описывается шаблоном: {param} подставляется в url (URL-экранирование), query/headers (как есть),
body_template (строки — с JSON-экранированием внутри кавычек, числа/boolean — сырым JSON).

По описанию пользователя верни ОДИН JSON-объект, без markdown:
{"slug": "...", "name": "...", "description": "...", "method": "GET",
 "url": "...", "headers": {}, "query": {}, "body_template": null,
 "content_type": "application/json",
 "parameters": [{"name": "...", "type": "string", "description": "...", "required": true, "enum": null}],
 "notes": "..."}

Правила:
- slug — латиница/цифры/дефис, ^[a-z0-9][a-z0-9-]{1,62}$; name — по-русски, до 80 символов; description — 1–2 предложения.
- method — GET|POST|PUT|PATCH|DELETE по смыслу операции.
- url — конкретный публичный https-адрес API с {param} там, где нужен путь.
- Используй ТОЛЬКО документированные параметры API. Не выдумывай флаги вида `temperature_2m=true`:
  если API выбирает поля отдельным параметром, передай его в query (например `hourly=temperature_2m,precipitation`,
  `current=temperature_2m`, `daily=temperature_2m_max`). Неизвестные параметры API молча игнорирует,
  и инструмент вернёт пустой/бесполезный ответ.
- Ответ инструмента попадает в контекст модели: запрашивай минимум полей и короткое окно
  (1–2 дня, несколько переменных), чтобы JSON был компактным — ориентир до ~2 КБ.
- headers — реальные имена заголовков; для секретов значение оставь пустой строкой.
- body_template — только для методов с телом: JSON-строка с {param} внутри кавычек, иначе null.
- parameters — максимум 6, name по шаблону ^[a-zA-Z_][a-zA-Z0-9_]{0,40}$, type string|number|integer|boolean.
- notes — что заполнить вручную (секреты, ключи, реальный URL), иначе пустая строка."""


SKILL_SYSTEM = """Ты — автор навыков для платформы ai-agents (формат skills.sh / SKILL.md).
Навык — это процедурные инструкции, которые добавляются к системному промпту агента.

По описанию пользователя верни ОДИН JSON-объект, без markdown вокруг:
{"name": "...", "slug": "...", "description": "...", "content": "...", "notes": "..."}

Правила:
- name — короткое название по-русски, до 80 символов.
- slug — латиница/цифры/дефис, ^[a-z0-9][a-z0-9-]{1,62}$; не повторяй занятые slug навыков.
- description — 1–2 предложения: что навык даёт агенту.
- content — полный SKILL.md на русском: YAML frontmatter с name и description, затем заголовок и разделы
  «## Когда использовать», «## Инструкции» (нумерованные шаги), «## Пример», «## Чек-лист».
  Пиши конкретные действия и критерии качества; без вымышленных API, путей и секретов. До ~4000 символов.
- notes — что уточнить у человека (иначе пустая строка)."""


def skill_prompt(description: str, used_slugs: list[str]) -> str:
    used = ", ".join(used_slugs[:MAX_CONTEXT_ITEMS]) or "(нет)"
    return (
        f"Описание навыка от пользователя:\n{description.strip()}\n\n"
        f"Занятые slug навыков: {used}"
    )


def _strip_fences(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def normalize_skill(
    raw: dict[str, Any], *, used_slugs: list[str]
) -> dict[str, Any]:
    warnings: list[str] = []
    name = str(raw.get("name") or "").strip()[:200]
    description = str(raw.get("description") or "").strip()[:2000]

    raw_slug = str(raw.get("slug") or "").strip()
    slug = raw_slug if SLUG_RE.match(raw_slug) else slugify(raw_slug or name)
    if not slug:
        warnings.append("slug не удалось вывести автоматически — заполните вручную")
    elif slug in set(used_slugs):
        slug = unique_slug(slug, set(used_slugs))
        warnings.append(f"slug был занят — предложен «{slug}»")

    content = _strip_fences(str(raw.get("content") or ""))[:40000]
    content = content.lstrip("\ufeff\u200b \t\r\n")
    had_frontmatter = bool(re.match(r"^---\s*\n.*?\n---\s*\n?", content, re.S))
    body = content
    # Срезаем ВСЕ frontmatter-блоки (модель иногда дублирует их) и голые name/description.
    while True:
        match = re.match(r"^---\s*\n.*?\n---\s*\n?", body, re.S)
        if not match:
            break
        body = body[match.end():].lstrip("\n")
    body = re.sub(r"^(?:\s*(?:name|description)\s*:[^\n]*\n)+", "", body).lstrip()
    if not had_frontmatter:
        warnings.append("добавлен YAML frontmatter шаблона skills.sh")
    if body:
        header = f"---\nname: {name or slug}\ndescription: {description}\n---\n\n"
        content = header + body.lstrip("\n")
    elif not content:
        warnings.append("модель не вернула содержимое SKILL.md — напишите его вручную")

    return {
        "name": name,
        "slug": slug,
        "description": description,
        "content": content,
        "notes": str(raw.get("notes") or "").strip()[:1000],
        "warnings": warnings,
    }


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return ""


def _squash(value: Any, limit: int = MAX_CONTEXT_CHARS) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []




def build_model(llm: LLMConfig | None = None) -> ChatOpenAI:
    """Тот же эндпоинт/модель/схема авторизации, что у тестовых запусков агентов."""
    project = project_llm()
    override = llm or LLMConfig()
    headers = auth_headers(
        override.api_key or project.api_key,
        override.auth_type or project.auth_type,
        override.auth_header or project.auth_header,
        override.auth_prefix
        if override.auth_prefix is not None
        else project.auth_prefix,
    )
    return ChatOpenAI(
        model=override.model or project.model,
        base_url=override.base_url or project.base_url,
        api_key="not-needed",
        default_headers=headers or None,
        temperature=ASSIST_TEMPERATURE,
        timeout=ASSIST_TIMEOUT_SECONDS,
        max_retries=0,
    )


async def complete_json(
    system: str, user: str, llm: LLMConfig | None = None
) -> dict[str, Any]:
    """One LLM round-trip that must yield a JSON object (single corrective retry)."""
    model = build_model(llm)
    messages: list[Any] = [SystemMessage(content=system), HumanMessage(content=user)]
    last_error: AssistError | None = None
    for attempt in range(2):
        try:
            response = await model.ainvoke(messages)
        except Exception as exc:  # noqa: BLE001 - report to the user, not to a traceback
            raise AssistError(f"LLM недоступен: {type(exc).__name__}: {exc}") from exc
        text = _text(response.content)
        try:
            return parse_json_object(text)
        except AssistError as exc:
            last_error = exc
            logger.warning(
                "LLM answer is not JSON (attempt {}): {}", attempt + 1, text[:400]
            )
            messages = [
                SystemMessage(content=system),
                HumanMessage(content=user),
                HumanMessage(
                    content=(
                        "Предыдущий ответ не был JSON-объектом. Верни ТОЛЬКО JSON по схеме "
                        "из системного сообщения: первый символ — '{', последний — '}', "
                        "без markdown, пояснений и текста вокруг."
                    )
                ),
            ]
    assert last_error is not None
    raise AssistError(f"{last_error}. Ответ модели: {text[:300]}")


def parse_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        raise AssistError("LLM вернул ответ без JSON-объекта")
    try:
        value = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AssistError(f"LLM вернул невалидный JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise AssistError("LLM вернул не JSON-объект")
    return value


def _tools_context(specs: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for spec in specs[:MAX_CONTEXT_ITEMS]:
        params = spec.get("parameters") or {}
        names = ", ".join(list((params.get("properties") or {}).keys())[:8])
        suffix = f" (параметры: {names})" if names else ""
        lines.append(f"- {spec.get('name')}: {_squash(spec.get('description'))}{suffix}")
    return "\n".join(lines) or "(доступных инструментов нет)"


def _skills_context(skills: list[Any]) -> str:
    lines: list[str] = []
    for skill in skills[:MAX_CONTEXT_ITEMS]:
        slug = getattr(skill, "slug", "")
        name = getattr(skill, "name", "") or slug
        description = _squash(getattr(skill, "description", ""))
        lines.append(f"- {slug}: {name}" + (f" — {description}" if description else ""))
    return "\n".join(lines) or "(доступных скиллов нет)"


def agent_prompt(
    description: str,
    tool_specs: list[dict[str, Any]],
    skills: list[Any],
    used_slugs: list[str],
) -> str:
    used = ", ".join(used_slugs[:MAX_CONTEXT_ITEMS]) or "(нет)"
    return (
        f"Описание агента от пользователя:\n{description.strip()}\n\n"
        f"Доступные инструменты:\n{_tools_context(tool_specs)}\n\n"
        f"Доступные скиллы:\n{_skills_context(skills)}\n\n"
        f"Занятые slug агентов: {used}"
    )


def tool_prompt(description: str) -> str:
    return f"Описание инструмента от пользователя:\n{description.strip()}"




def normalize_agent(
    raw: dict[str, Any],
    *,
    known_tools: list[str],
    known_skills: list[str],
    used_slugs: list[str],
    reserved_tools: list[str] | None = None,
) -> dict[str, Any]:
    """Keep only names that exist; sanitize slug; collect human-readable warnings."""
    warnings: list[str] = []
    known_tool_set = set(known_tools)
    reserved_tool_set = set(reserved_tools or known_tools)
    known_skill_set = set(known_skills)

    tools: list[str] = []
    for item in _as_list(raw.get("tools")):
        name = str(item or "").strip()
        if not name:
            continue
        if name not in known_tool_set:
            warnings.append(f"инструмент «{name}» не найден среди доступных — пропущен")
            continue
        if name not in tools:
            tools.append(name)

    skills: list[str] = []
    for item in _as_list(raw.get("skills")):
        slug = str(item or "").strip()
        if not slug:
            continue
        if slug not in known_skill_set:
            warnings.append(f"скилл «{slug}» не импортирован — пропущен")
            continue
        if slug not in skills:
            skills.append(slug)

    new_tools: list[dict[str, str]] = []
    for item in _as_list(raw.get("new_tools"))[:3]:
        if not isinstance(item, dict):
            continue
        candidate = str(item.get("slug") or item.get("name") or "").strip()
        slug = candidate if SLUG_RE.match(candidate) else slugify(candidate)
        if not slug:
            continue
        if slug in reserved_tool_set:
            warnings.append(f"инструмент «{slug}» уже существует — предложение пропущено")
            continue
        if any(entry["slug"] == slug for entry in new_tools):
            continue
        new_tools.append(
            {
                "slug": slug,
                "name": str(item.get("name") or slug)[:200],
                "description": str(item.get("description") or "")[:2000],
                "note": str(item.get("note") or "")[:2000],
            }
        )

    raw_slug = str(raw.get("slug") or "").strip()
    slug = raw_slug if SLUG_RE.match(raw_slug) else slugify(raw_slug or str(raw.get("name") or ""))
    if not slug:
        warnings.append("slug не удалось вывести автоматически — заполните вручную")
    elif slug in set(used_slugs):
        slug = unique_slug(slug, set(used_slugs))
        warnings.append(f"slug был занят — предложен «{slug}»")

    return {
        "name": str(raw.get("name") or "").strip()[:200],
        "slug": slug,
        "description": str(raw.get("description") or "").strip()[:4000],
        "system_prompt": str(raw.get("system_prompt") or "").strip()[:20000],
        "tools": tools,
        "skills": skills,
        "new_tools": new_tools,
        "notes": str(raw.get("notes") or "").strip()[:2000],
        "warnings": warnings,
    }


def _str_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for key, item in list(value.items())[:20]:
        name = str(key or "").strip()
        if name:
            result[name] = "" if item is None else str(item)
    return result


def normalize_tool(raw: dict[str, Any], *, used_slugs: list[str]) -> dict[str, Any]:
    warnings: list[str] = []

    raw_slug = str(raw.get("slug") or "").strip()
    slug = raw_slug if SLUG_RE.match(raw_slug) else slugify(raw_slug or str(raw.get("name") or ""))
    if not slug:
        warnings.append("slug не удалось вывести автоматически — заполните вручную")
    elif slug in set(used_slugs):
        slug = unique_slug(slug, set(used_slugs))
        warnings.append(f"slug был занят — предложен «{slug}»")

    method = str(raw.get("method") or "GET").strip().upper()
    if method not in TOOL_METHODS:
        warnings.append(f"метод «{method}» не поддерживается — выставлен GET")
        method = "GET"

    url = str(raw.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        if url:
            warnings.append("URL не похож на http(s) — проверьте вручную")
        url = url if url.startswith(("http://", "https://")) else ""

    parameters: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _as_list(raw.get("parameters"))[:6]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not PARAM_NAME_RE.match(name):
            if name:
                warnings.append(f"параметр «{name}» имеет недопустимое имя — пропущен")
            continue
        if name in seen:
            continue
        seen.add(name)
        param_type = str(item.get("type") or "string").strip().lower()
        if param_type not in TOOL_TYPES:
            warnings.append(f"тип «{param_type}» у параметра «{name}» заменён на string")
            param_type = "string"
        enum = [str(value) for value in _as_list(item.get("enum")) if str(value).strip()][:20]
        parameters.append(
            {
                "name": name,
                "type": param_type,
                "description": str(item.get("description") or "")[:500],
                "required": bool(item.get("required", True)),
                "enum": enum or None,
            }
        )
    if not parameters:
        warnings.append("параметры не определены — добавьте вручную, если инструменту нужны аргументы")

    body_template = raw.get("body_template")
    body_text = str(body_template).strip() if isinstance(body_template, str) else ""
    if method in {"GET", "DELETE"} and body_text:
        warnings.append("body_template игнорируется для методов GET/DELETE")

    notes = str(raw.get("notes") or "").strip()[:2000]
    if any(value == "" for value in _str_map(raw.get("headers")).values()) and not notes:
        notes = "Заполните значения заголовков-секретов вручную."

    return {
        "slug": slug,
        "name": str(raw.get("name") or "").strip()[:200],
        "description": str(raw.get("description") or "").strip()[:4000],
        "method": method,
        "url": url[:2000],
        "headers": _str_map(raw.get("headers")),
        "query": _str_map(raw.get("query")),
        "body_template": body_text[:8000] or None,
        "content_type": str(raw.get("content_type") or "application/json")[:120],
        "parameters": parameters,
        "notes": notes,
        "warnings": warnings,
    }


# --- Чат-ассистент по всему сервису -------------------------------------------------

CHAT_MODES = ("form", "advice", "review", "test")

# Поля, которые ассистент может заполнить в форме (всё остальное отбрасывается).
FORM_FIELDS: dict[str, tuple[str, ...]] = {
    "agent": (
        "name",
        "slug",
        "description",
        "system_prompt",
        "tools",
        "skills",
        "limits",
        "llm",
        "page_search",
    ),
    "tool": (
        "slug",
        "name",
        "description",
        "method",
        "url",
        "headers",
        "query",
        "body_template",
        "content_type",
        "parameters",
        "timeout_seconds",
        "enabled",
        "page_search",
    ),
    "llm": ("name", "base_url", "model", "auth_type", "auth_header", "auth_prefix", "page_search"),
    "mcp-connection": (
        "slug",
        "name",
        "description",
        "url",
        "headers",
        "timeout_seconds",
        "enabled",
        "page_search",
    ),
    "mcp-server": (
        "slug",
        "name",
        "description",
        "agent_slugs",
        "tool_slugs",
        "skill_slugs",
        "page_search",
    ),
    "skill": ("name", "slug", "description", "content", "page_search"),
    "user": ("app_role", "daily_run_limit", "page_search"),
    "service-keys": ("page_search",),
    "general": ("page_search",),
}

TARGET_HINT = {
    "agent": (
        "раздел /agents и редактор агента: форма (name, slug, description, system_prompt, tools, skills, "
        "limits, llm) плюс каталог агентов/tools/skills в контексте. "
        "На списке агентов есть поле поиска — верни page_search для фильтрации строк таблицы/карточек. "
        "Поиск «агент про X» — по блоку «Агенты»; tools/skills в fields — только из каталога."
    ),
    "tool": (
        "раздел /tools: форма HTTP-инструмента (slug, name, method, url, headers, query, "
        "body_template, content_type, parameters, timeout_seconds, enabled) и каталог "
        "установленных инструментов. На списке инструментов есть поле поиска — page_search."
    ),
    "llm": (
        "раздел /admin/llm: форма LLM-провайдера "
        "(name, base_url, model, auth_type=bearer|header|none, auth_header, auth_prefix). "
        "Секреты/api_key не выдумывай. Список провайдеров фильтруется через page_search."
    ),
    "mcp-connection": (
        "вкладка MCP-подключений внутрь: форма (slug, name, description, url, headers, "
        "timeout_seconds, enabled). Tools агентам доступны как mcp:<slug>:<tool>. "
        "Список подключений — page_search."
    ),
    "mcp-server": (
        "вкладка MCP-серверов наружу: форма slug/name/description/agent_slugs/tool_slugs/skill_slugs. "
        "Ключ генерирует сервер после create — не выдумывай. Один ключ = один клиент; "
        "allowlist fail-closed (пустой список категории = deny). "
        "В current могут быть taken_slugs, endpoint и published_agents. Список серверов — page_search."
    ),
    "skill": (
        "раздел /skills: форма навыка SKILL.md (name, slug, description, content) "
        "и каталог уже установленных навыков. Поле поиска по установленным — page_search. "
        "При поиске «навык про X / git / …» смотри блок «Установленные навыки» — отвечай slug+название+зачем; "
        "не отсылай к find-skills и не предлагай создавать заново то, что уже в каталоге."
    ),
    "user": (
        "раздел /admin/users: форма роли (app_role=superadmin|admin|user, daily_run_limit). "
        "Не выдумывай email/пароли — только роль и лимит. Таблица пользователей — page_search."
    ),
    "service-keys": (
        "раздел /admin/keys: таблица сервисных API-ключей (имя, скоупы, allowlist). "
        "Только page_search для фильтрации строк таблицы."
    ),
    "general": (
        "страница без своей формы (runs, stats, docs, about, настройки без формы провайдера). "
        "Только подсказки; для фильтрации списка на странице со своим полем поиска — верни fields с page_search."
    ),
}

CHAT_SYSTEM = """Ты — встроенный ассистент платформы ai-agents (FastAPI + LangGraph, агенты, инструменты, скиллы, MCP, LLM-провайдеры, роли).
Пользователь задаёт вопрос обычным текстом на любой странице UI; ты полезен и в подсказках, и в заполнении форм.

Режимы:
- form — заполнить/улучшить поля ТЕКУЩЕЙ формы по описанию: верни готовые значения в fields.
- advice — объяснить шаг или ответить по каталогу/странице (без изменения полей → fields=null).
- review — проверить текущую конфигурацию (current) и указать конкретные проблемы и правки.
- test — предложить, как проверить работу (тестовые промпты, ожидаемые события, что смотреть в запуске).

Отвечай ОДНИМ JSON-объектом, без markdown:
{"answer": "текст по-русски для человека (2–6 предложений или список через \\n)",
 "fields": { ... } | null,
 "warnings": ["..."]}

Правила:
- answer — кратко и по делу; если предлагаешь поля — перечисли ключевые в answer.
- fields — только в режиме form и только ключи, перечисленные для текущей формы; иначе null.
- Поле page_search (строка, допустимо на любой странице с фильтром): подстрока для поля поиска в UI.
  Если пользователь просит «найди на странице», «отфильтруй», «что за агент/инструмент про…»
  — верни {"page_search": "…"} с ключевыми словами (латиница/кириллица как в карточках);
  можно сочетать с другими полями формы.
- Режим form + просьба создать/заполнить («сделай агента…», «заполни инструмент…») → обязательно
  непустые fields по допустимым ключам; опирайся на каталог для tools/skills/*_slugs.
- Режим form, но пользователь только спрашивает «что есть / найди в каталоге» без заполнения →
  fields=null и перечисли подходящие записи из контекста (исключение: запрос «отфильтруй/найди на странице» —
  тогда только page_search в fields).
- Никогда не выдумывай секреты и токены: для ключей оставляй пустую строку и пиши в warnings.
- tools/skills/agent_slugs/tool_slugs/skill_slugs в fields — только имена из переданного каталога;
  если нужного нет — предложи создать (в warnings), не подставляй выдуманное.
- Если пользователь просит найти, перечислить или подсказать агентов / инструменты / навыки / MCP
  по теме или «на этой странице» — отвечай по каталогу из «Контекст сервиса»: slug + name/description
  и почему подходит. Не предлагай создавать заново то, что уже есть. Не путай установленный каталог
  с поиском на skills.sh (find-skills).
- Не обещай функций, которых нет в переданной информации о сервисе.
- warnings — до 3 пунктов: что проверить/заполнить вручную (иначе [])."""


CHAT_CONTEXT_LIMIT = 6000


def chat_prompt(
    *,
    mode: str,
    target: str,
    message: str,
    current: dict[str, Any] | None,
    history: list[dict[str, str]] | None,
    context: str = "",
) -> str:
    parts = [
        f"Режим: {mode}.",
        f"Форма/раздел: {TARGET_HINT.get(target, target)}.",
        f"Допустимые поля: {', '.join(FORM_FIELDS.get(target, ())) or '(нет)'}.",
    ]
    if context:
        parts.append(f"Контекст сервиса:\n{_squash(context, CHAT_CONTEXT_LIMIT)}")
    if current:
        parts.append(
            "Текущие значения формы (JSON):\n"
            + json.dumps(current, ensure_ascii=False, default=str)[:3000]
        )
    if history:
        lines = [
            f"{item.get('role', 'user')}: {_squash(item.get('content'), 400)}"
            for item in history[-8:]
        ]
        parts.append("Предыдущие сообщения:\n" + "\n".join(lines))
    parts.append(f"Запрос пользователя: {message}")
    return "\n\n".join(parts)


def _clean_scalar(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


def normalize_chat_fields(target: str, raw: Any) -> dict[str, Any] | None:
    """Оставить только разрешённые поля формы и привести простые типы."""
    if not isinstance(raw, dict):
        return None
    allowed = FORM_FIELDS.get(target, ())
    if not allowed:
        return None
    cleaned: dict[str, Any] = {}
    for key in allowed:
        if key not in raw or raw[key] is None:
            continue
        value = raw[key]
        if key in {
            "tools",
            "skills",
            "agent_slugs",
            "tool_slugs",
            "skill_slugs",
        }:
            value = [str(item) for item in _as_list(value) if isinstance(item, str)]
        elif key == "parameters":
            value = [item for item in _as_list(value) if isinstance(item, dict)]
        elif key in {"headers", "query", "limits", "llm"}:
            value = value if isinstance(value, dict) else None
            if value is None:
                continue
        elif key in {"timeout_seconds", "daily_run_limit"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                try:
                    value = int(str(value).strip())
                except (TypeError, ValueError):
                    continue
        elif key == "enabled":
            if not isinstance(value, bool):
                continue
        elif key == "page_search":
            value = _clean_scalar(value)
            if not isinstance(value, str) or not value:
                continue
            value = value[:500]
        elif isinstance(value, (dict, list)):
            continue
        else:
            value = _clean_scalar(value)
            if not isinstance(value, str):
                continue
        cleaned[key] = value
    return cleaned or None


def normalize_chat(raw: dict[str, Any], *, target: str) -> dict[str, Any]:
    answer = _squash(raw.get("answer") or raw.get("text") or "", 4000)
    warnings = [
        _squash(item, 300) for item in _as_list(raw.get("warnings")) if str(item).strip()
    ][:3]
    return {
        "answer": answer or "Модель не вернула текста — попробуйте переформулировать запрос.",
        "fields": normalize_chat_fields(target, raw.get("fields")),
        "warnings": warnings,
    }


async def chat_reply(
    *,
    mode: str,
    target: str,
    message: str,
    current: dict[str, Any] | None,
    history: list[dict[str, str]] | None,
    context: str = "",
    llm: LLMConfig | None = None,
) -> dict[str, Any]:
    raw = await complete_json(
        CHAT_SYSTEM,
        chat_prompt(
            mode=mode,
            target=target,
            message=message,
            current=current,
            history=history,
            context=context,
        ),
        llm,
    )
    return normalize_chat(raw, target=target)
