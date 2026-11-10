# Как подключить внешнее приложение к ai-agents

Краткая инструкция для интеграций. Полный контракт — [`API.md`](API.md).

Основные способы:

| Способ | Когда выбирать |
|---|---|
| **REST catalog / invoke / runs** | фабрика и оркестраторы: skills+tools без LLM ai-agents, эксперты через SSE |
| **REST `/v1/*`** + Bearer | CRUD агентов, batch, полный control plane |
| **MCP `/mcp`** | Cursor / Claude Desktop: агенты, `tool__*`, `get_skill` |

Базовые URL:

| Контур | URL |
|---|---|
| Lab/work | `https://ai-agents-dev.example.com` |
| Prod | `https://ai-agents.example.com` |
| Local / Cursor на хосте | `http://127.0.0.1:8096` |
| Compose peer (BFF и т.п.) | `http://host.docker.internal:8096` |

MCP-клиент передаёт обычный `Host` из URL. Allowlist DNS-rebinding на `/mcp` включает FQDN из `PUBLIC_URL`, `localhost`/`127.0.0.1` и Docker Desktop aliases (`host.docker.internal`). Доп. хосты — `MCP_ALLOWED_HOSTS`. Подмена `Host` в клиенте не нужна.

---

## 1. REST API (сервисный ключ)

### 1.1. Получить ключ

1. Войти в UI под **суперадмином**.
2. Раздел **«Сервисные ключи»** → создать ключ со скоупами под задачу:
   - запуск экспертов: `agents:read`, `runs:read`, `runs:execute`;
   - гибрид (фабрика): ещё `tools:read`, `tools:execute`, `skills:read` — **без** `*:write`;
   - CRUD каталога: `agents:write` / `tools:write` / `skills:write` по нужным сущностям;
   - настройки LLM / админ: `admin`.
3. Ключ показывается **один раз** — сохранить в секрет хранилища приложения.

Альтернатива для lab: bootstrap-ключ из `SERVICE_API_KEYS` (полный доступ). В prod для внешних систем предпочтительны ключи из БД с минимальными скоупами.

### 1.2. Вызов

```http
Authorization: Bearer <SERVICE_API_KEY>
Content-Type: application/json
```

Минимальный сценарий «спросить агента»:

```bash
BASE=https://ai-agents-dev.example.com
KEY=...

# 1) Список доступных агентов (shared + published)
curl -s "$BASE/v1/agents?scope=shared" -H "Authorization: Bearer $KEY"

# 2) Запуск
RUN_ID=$(curl -s -X POST "$BASE/v1/runs" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"agent_id":"echo-tools","input":"17*4+9","metadata":{"source":"my-app"}}' \
  | sed -E 's/.*"run_id":"([^"]+)".*/\1/')

# 3a) Стрим событий (рекомендуется для UI)
curl -sN "$BASE/v1/runs/$RUN_ID/events" -H "Authorization: Bearer $KEY"

# 3b) Или поллинг финала
curl -s "$BASE/v1/runs/$RUN_ID" -H "Authorization: Bearer $KEY"
```

Ответ `POST /v1/runs` (201): `run_id`, `status` (`queued` → `running` → `succeeded`/`failed`/`cancelled`), позже `output` / `error`.

### 1.3. SSE-события

`GET /v1/runs/{run_id}/events?after=<seq>` — сначала история из БД, затем live до терминального статуса.

| event | смысл |
|---|---|
| `run.started` | старт |
| `message.delta` | кусок текста ответа |
| `tool.call` / `tool.result` | вызов инструмента |
| `run.completed` | финал в `output` |
| `run.failed` / `run.cancelled` | ошибка / отмена |

Докачка после обрыва: передать `after` = последний полученный `id:` (seq).

Отмена: `POST /v1/runs/{run_id}/cancel`.

### 1.4. Важные ограничения

- Запускать можно только **опубликованного** агента (`status=published`). Иначе `409`.
- Сервисный ключ видит чужих агентов только если они `shared` + `published`.
- `agent_id` в теле — `slug` или UUID.
- Чужой/невидимый run → `404` (не `403`).
- Секреты (`api_key` LLM) в теле рана в БД не сохраняются; для прод-запусков обычно достаточно активного LLM-провайдера на стороне ai-agents.

### 1.5. Типичная обёртка во внешнем приложении

```text
1. Хранить BASE + KEY в секретах приложения
2. (опционально) кэшировать GET /v1/agents?scope=shared
3. POST /v1/runs { agent_id, input, metadata }
4. Подписаться на /events или поллить GET /v1/runs/{id} до терминального статуса
5. Взять output / error; при необходимости POST .../cancel по таймауту клиента
```

OpenAPI/Swagger: `{BASE}/docs` → Authorize → `ServiceBearer`.

---

## 2. Гибрид для «умного» бэкенда (фабрика)

Канон: LLM клиента + каталог/invoke/runs ai-agents.

1. Суперадмин → **Сервисные ключи**: scopes
   `agents:read`, `tools:read`, `tools:execute`, `skills:read`, `runs:read`, `runs:execute`
   + allowlist `agent_slugs` / `tool_slugs` / `skill_slugs` (fail-closed: пусто = deny категории).
   Не выдавайте `*:write`, если клиент не должен менять каталог.
2. `GET /v1/catalog` — что можно делегировать (секции по `*:read`).
3. Skill в контекст клиента: `GET /v1/skills/{slug}` → `content` (`skills:read`).
4. Atomic tool: `POST /v1/tools/{slug}/invoke` `{"params":{…}}` → `{ok, output}`
   (`tools:execute`, без LLM ai-agents).
5. Expert: `POST /v1/runs` + `GET /v1/runs/{id}/events` (SSE, `runs:execute`),
   не долгий blocking MCP call.

Env bootstrap `SERVICE_API_KEYS` — полный доступ к catalog (без allowlist).

## 3. Общий MCP (IDE и «тонкие» клиенты)

ai-agents — **MCP-сервер** (Streamable HTTP). Allowlist ключа: `agent_slugs`, `tool_slugs`,
`skill_slugs` (категории независимо). Агенты — published+shared.

### 3.1. Выдать MCP-ключ

1. UI → **MCP** → вкладка **«Серверы»** (суперадмин).
2. Создать запись и выбрать агентов / tools / skills — JSON для клиента (ключ `mcp-ag-…` один раз).
3. URL: `{PUBLIC_URL}/mcp` (lab: `https://ai-agents-dev.example.com/mcp`).

### 3.2. Подключить клиент

**Cursor / Claude Desktop / Claude Code** (фабрика предпочтительнее REST §2):

```json
{
  "mcpServers": {
    "ai-agents": {
      "url": "https://ai-agents-dev.example.com/mcp",
      "headers": {
        "Authorization": "Bearer mcp-ag-…"
      }
    }
  }
}
```

Lab Compose: `"url": "http://host.docker.internal:8096/mcp"`.

В `tools/list`: агенты (`prompt`), atomic `tool__{slug}`, при skills — `get_skill`.
Вызов агента = `POST /v1/runs` → финальный текст; `tool__*` = invoke без LLM.

### 3.3. Владелец агента

1. Создать агента, tools/skills → publish `shared`.
2. Добавить slug в `agent_slugs` MCP-ключа.

### 3.4. Один MCP на много клиентов

```text
Приложение A (ключ A)  ─┐
Приложение B (ключ B)  ─┼─►  POST /mcp
Cursor (ключ C)        ─┘
```

- IDE / тонкий клиент — MCP; оркестратор со стримом — REST §1–2.

---

## 4. Что не путать

| Направление | Суть |
|---|---|
| **MCP наружу** (`/mcp`, ключи `mcp-ag-…`) | внешние клиенты вызывают **наших** агентов / tools / skills |
| **MCP внутрь** (`/v1/mcp-connections`) | **наши** агенты вызывают инструменты чужих MCP-серверов |
| **REST catalog / invoke** | фабрика: skills+tools без LLM ai-agents; experts через `/v1/runs` |

---

## 5. Чеклист интеграции

- [ ] Выбран контур (lab / prod) и `BASE`
- [ ] Выдан сервисный ключ (с allowlist) **или** MCP-ключ; ключ в секретах
- [ ] Нужные агенты published+shared; tools/skills в allowlist ключа
- [ ] Smoke: catalog + invoke **или** REST run + SSE **или** MCP `tools/list`
- [ ] В `metadata` рана (REST) указан источник (`source`, id пользователя внешней системы)
- [ ] Дневной лимит только для роли `user`; service/MCP — машинные principal’ы

Подробности ошибок, лимитов, схем тел — [`API.md`](API.md).
