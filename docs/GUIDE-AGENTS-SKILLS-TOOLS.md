# Как создавать агентов, навыки и инструменты

Практическая инструкция для UI и API. Контракт полей — [`API.md`](API.md).

Роли: создавать и публиковать могут `admin` и `superadmin`. Роль `user` только смотрит и тестирует **опубликованные общие** агенты.

Рекомендуемый порядок сборки:

```text
1. Инструменты (что агент умеет вызывать)
2. Навыки (как действовать — SKILL.md)
3. Агент (промпт + привязка tools/skills) → тест → публикация
```

---

## 1. Инструменты

Инструмент — действие, которое модель может вызвать во время запуска (калькулятор, HTTP API, tool внешнего MCP).

Раздел UI: **«Инструменты»** (`/tools`).

### 1.1. Встроенные

Всегда доступны (привязка по имени):

| Имя | Назначение |
|---|---|
| `calculator` | арифметика (allowlist символов) |
| `now` | текущее время (IANA tz / алиасы `moscow`, `minsk`, `utc+3`) |
| `get_server_time` | время сервера |

Их создавать не нужно — достаточно отметить в редакторе агента.

### 1.2. Свой HTTP-инструмент (без кода)

UI: **Инструменты** → «Создать» (или AI-панель → режим form).

Заполните:

| Поле | Пример |
|---|---|
| slug | `weather` (латиница, `-`, неизменяем после создания) |
| name / description | понятные модели и человеку |
| method + url | `GET https://api.example/geo/{city}` |
| parameters | список аргументов (`string` / `number` / `integer` / `boolean`) |
| query / headers / body_template | шаблоны с `{param}` |
| timeout | 1…60 с |

Правила:

- В URL плейсхолдеры только в path/query, не в host.
- Только `http(s)`; private/loopback/metadata запрещены (SSRF-guard).
- Секреты кладите в `headers`; API наружу отдаёт только имена заголовков (`header_names`).
- После сохранения нажмите **«Проверить»** с тестовыми `params`.

Эквивалент API:

```bash
curl -X POST "$BASE/v1/tools" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{
    "slug": "weather",
    "name": "Weather",
    "description": "Прогноз погоды",
    "method": "POST",
    "url": "https://api.example/geo/{city}",
    "headers": {"X-Key": "secret"},
    "body_template": "{\"city\": \"{city}\", \"days\": {days}}",
    "content_type": "application/json",
    "parameters": [
      {"name": "city", "type": "string", "required": true},
      {"name": "days", "type": "integer", "required": false}
    ],
    "timeout_seconds": 20,
    "enabled": true
  }'
```

Имя в списке `agents.tools` = **slug**. Правка custom-инструмента действует на **следующие запуски сразу**, без перепубликации агента. Выключенный/удалённый инструмент нельзя привязать или переопубликовать агента (`422`); при удалении он отвязывается от всех агентов.

AI-подсказка: `POST /v1/assist/tool` `{"description": "…"}` или кнопка AI в форме.

### 1.3. Инструменты внешнего MCP

Если нужный tool уже есть у другого MCP-сервера (Streamable HTTP):

1. UI → **MCP** → вкладка **«Подключения»** → создать (`url`, опционально `Authorization` в headers).
2. **«Проверить»** — подтянется список tools.
3. В агенте в `tools` указать ссылку вида:

```text
mcp:<connection-slug>:<tool-name>
```

Пример: `mcp:internal-docs:search`.

stdio-MCP в backend не поддерживается (только Streamable HTTP).

### 1.4. Локальный Docker MCP Gateway

Docker MCP Gateway умеет отдавать тот же транспорт по HTTP — отдельный stdio-режим не нужен:

```bash
# на Docker-хосте: локальные MCP-серверы как Streamable HTTP на /mcp
docker mcp gateway run --transport streaming --port 8811 --host 0.0.0.0 --servers <name>
# вместо --servers <name> можно --enable-all-servers
```

В UI «MCP» → подключение: URL `http://host.docker.internal:8811/mcp`, заголовки:

```text
Authorization: Bearer <MCP_GATEWAY_AUTH_TOKEN>   # если токен задан
Host: 127.0.0.1:8811                             # gateway пускает только localhost/127.0.0.1
```

Gateway проверяет `Host` (защита от DNS-rebinding) и отвергает `host.docker.internal`
(`403 invalid Host header`), поэтому заголовок `Host` из URL нужно переопределить.

Токен не выдаётся Docker'ом: это произвольный секрет, который вы задаёте сами при запуске
gateway (`MCP_GATEWAY_AUTH_TOKEN=... docker mcp gateway run ...`); без него нужен
`--allow-unauthenticated` (только loopback).

Приватный адрес (`host.docker.internal`, `10.x`, `192.168.x`) разрешён только явно:
`MCP_EGRESS_ALLOWED_HOSTS=host.docker.internal` (env backend; действует только на MCP).

---

## 2. Навыки (skills)

Навык — текст `SKILL.md` (процедурное знание), который при запуске **добавляется к system prompt**. Это не исполняемый код и не HTTP-вызов.

Раздел UI: **«Навыки»** (`/skills`).

### 2.1. Свой навык вручную

1. **Навыки** → создать.
2. Указать name / description; slug можно оставить авто из названия.
3. В `content` — полный SKILL.md (желательно с YAML frontmatter skills.sh: `name`, `description`).
4. Сохранить. Источник: `manual` — такой навык потом можно править через UI/`PATCH`.

API:

```bash
curl -X POST "$BASE/v1/skills" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{
    "name": "Краткий ответ",
    "slug": "brief-reply",
    "description": "Отвечать коротко и по делу",
    "content": "---\nname: brief-reply\ndescription: Краткость\n---\n\n# Правила\n- 2–4 предложения\n- без воды\n"
  }'
```

Генерация черновика: AI-панель на странице навыков или `POST /v1/assist/skill` `{"description": "…"}`.

### 2.2. Импорт с skills.sh

1. Взять URL вида `https://skills.sh/<owner>/<repo>/<skill>`.
2. UI → импорт по ссылке **или**

```bash
curl -X POST "$BASE/v1/skills/import" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"url":"https://skills.sh/vercel-labs/agent-skills/web-design-guidelines"}'
```

Повторный импорт того же `source_id` обновляет контент. Поиск `GET /v1/skills/search?q=` работает только при настроенном `SKILLS_SH_TOKEN`; без него используйте импорт по URL.

Импортированные навыки (`source=skills.sh`) правятся **повторным импортом**, не через `PATCH`.

### 2.3. Импорт с компьютера

UI: выбрать файл `.md` / `SKILL.md` или папку — браузер читает содержимое и шлёт `POST /v1/skills/import-local` с `entries` (не путь Windows на сервер).

### 2.4. Привязка к агенту

В редакторе агента отметьте навыки — в API это `skills: ["brief-reply", "frontend-design"]`.

При **публикации** тела скиллов пишутся в snapshot (история/rollback). На запуске тела
берутся **live из БД**: правка навыка сразу действует на следующий run; в UI появится
бейдж «навыки» (`skills_stale`), пока снова не опубликуете (обновится snapshot).

---

## 3. Агенты

Агент = system prompt + набор tools/skills + (опционально) LLM/лимиты. Запуск требует
**опубликованного** агента: prompt/LLM/limits — из snapshot версии; тела skills/tools — live.

Раздел UI: **«Агенты»** (`/agents`) → создать / открыть редактор.

### 3.1. Создать preset-агента

1. Имя, slug (`^[a-z0-9][a-z0-9-]{1,62}$`, после создания slug не меняется).
2. **System prompt** — роль и правила (обязателен для `kind=preset`).
3. Отметить **инструменты** (builtin / custom / `mcp:…`) и **навыки**.
4. При необходимости: модель/temperature (пусто = активный провайдер проекта), `max_steps`, `timeout_seconds`.
5. Сохранить → получите **draft**.
6. На странице агента: **тест** (создаст run) → при успехе **Опубликовать**.
   - `private` — только владелец (и суперадмин);
   - `shared` — виден сервисам, роли `user`; во внешнем **MCP** (`/mcp`) — только если slug в allowlist ключа.

API:

```bash
# Создать
curl -X POST "$BASE/v1/agents" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{
    "slug": "smoke-calc",
    "name": "Калькулятор",
    "description": "Считает выражения",
    "kind": "preset",
    "system_prompt": "Ты калькулятор. Используй tool calculator. Отвечай только результатом.",
    "tools": ["calculator"],
    "skills": [],
    "llm": {"temperature": 0.2},
    "limits": {"max_steps": 4, "timeout_seconds": 60}
  }'

# Опубликовать для внешних систем / MCP
curl -X POST "$BASE/v1/agents/smoke-calc/publish" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"visibility":"shared"}'
```

AI-черновик формы: кнопка AI в редакторе или `POST /v1/assist/agent` `{"description": "…"}`.

### 3.2. Что менять с publish, а что без

| Изменение | Нужен publish? |
|---|---|
| system prompt, LLM / limits, kind | **да** (из snapshot версии) |
| список skills / tools у агента | желателен publish (в snapshot для истории); **резолв тел на run — live из БД** |
| правка тела skill (`PATCH /v1/skills`) | **нет** — сразу на следующий run; появится бейдж `skills_stale` |
| правка URL/headers custom-инструмента | **нет** — сразу на следующий run; `tools_stale` |
| перепубликация | обновляет snapshot `skill_defs`/`tool_defs` и гасит stale-бейджи |

Фильтр списка: `GET /v1/agents?stale=any` (или `skills` / `tools`).

Откат: `POST /v1/agents/{ref}/rollback` с номером версии — копирует snapshot в агента и **публикует новую** версию (история не переписывается).

Клон: `POST /v1/agents/{ref}/clone` — приватный draft `…-copy-…`.

Архив: `DELETE /v1/agents/{ref}` — запуск запрещён, из списков скрыт.

### 3.3. Проверка перед отдачей наружу

1. Тестовый run в UI или `POST /v1/runs` + SSE.
2. Убедиться, что tools вызываются (`tool.call` / `tool.result`), ответ адекватен.
3. Опубликовать `shared`, если агент нужен внешним приложениям или MCP.
4. Для MCP: добавить slug в allowlist ключа (UI MCP → Серверы); проверить `tools/list` у клиента.

---

## 4. Мини-сценарий «агент для внешней системы»

```text
1. Создать HTTP-tool (или взять builtin / mcp:…)
2. При необходимости — навык с регламентом ответа
3. Создать агента: промпт + tools + skills
4. Протестировать в UI
5. Опубликовать visibility=shared
6. Отдать интеграторам:
   - REST: BASE + service key + slug агента  → см. GUIDE-EXTERNAL-API.md
   - или MCP: URL /mcp + ключ mcp-ag-…     → агент появится как tool
```

---

## 5. Частые ошибки

| Симптом | Причина |
|---|---|
| `409 agent is not published` | забыли publish |
| Агента нет в MCP / у service key | не `shared`, только `private` |
| `422` при publish / сохранении | в `tools` мёртвый/выключенный slug или битый `mcp:…` |
| Правка skill «не действует» | смотрите **новый** run; бейдж «навыки» — только про snapshot, не про live |
| Правка HTTP-tool «не действует» | проверьте тот же slug; смотрите новый run, не старый |
| `exceeds the available context size` | ответ tool слишком большой для окна модели — урежьте ответ API |
| `403` / нет пунктов меню | роль `user` не создаёт agents/tools/skills |

Дальше: внешние подключения — [`GUIDE-EXTERNAL-API.md`](GUIDE-EXTERNAL-API.md); полный справочник — [`API.md`](API.md).
