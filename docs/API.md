# API — ai-agents control plane

Управление агентами и их запуск: `POST /v1/runs` + SSE, CRUD/публикация агентов,
Keycloak OIDC для людей (BFF-cookie) и сервисные Bearer-ключи для машин.
Практические гайды: [`GUIDE-EXTERNAL-API.md`](GUIDE-EXTERNAL-API.md) (REST/MCP для внешних приложений),
[`GUIDE-AGENTS-SKILLS-TOOLS.md`](GUIDE-AGENTS-SKILLS-TOOLS.md) (создание агентов, навыков, инструментов).
Продуктовая админка — React+Mantine (`frontend/`), FQDN:

- lab/work: `https://ai-agents-dev.example.com`
- prod k8s: `https://ai-agents.example.com`
- local: `http://localhost:8096` (API) / `http://localhost:5173` (Vite) / `http://localhost:4196` (nginx)

## Auth

### Service Bearer (`/v1/*`)

```http
Authorization: Bearer <SERVICE_API_KEY>
```

- Bootstrap-ключи — `SERVICE_API_KEYS` (comma/space separated), только `docker/.env.secrets` / k8s Secret; полный доступ (`is_superadmin=true`).
- Ключи из БД (`service_keys`, UI `/api/admin/service-keys`) — подмножество скоупов:
  `agents:read|write`, `tools:read|execute|write`, `skills:read|write`, `runs:read|execute`, `admin`.
  - `*:read` — смотреть ресурс / секцию каталога; `*:write` — CRUD; `*:execute` — действие
    (invoke tool / старт run), **не** правка каталога.
  - Legacy `runs:write` при создании/загрузке ключа нормализуется в `runs:execute`.
- Нет ключа/неверный → `401`; ни env-ключей, ни включённых DB-ключей → `503`.
- `PATCH /api/admin/service-keys/{id}` меняет `scopes`, allowlists, имя и `enabled` **без смены ключа**:
  отзыв — `enabled=false`, восстановление — `enabled=true`; значение Bearer-ключа сохраняется, пока строка не удалена.
  Изменение scopes действует со следующего запроса с этим ключом.
- Схема объявлена в OpenAPI (`ServiceBearer`): в Swagger UI (`/docs`) кнопка **Authorize** принимает ключ, после чего «Try it out» на `/v1/*` работает с ним.

### Cookie-сессия (UI, `/auth/*`, `/api/admin/*`)

- `GET /auth/login?return_to=/agents` → `302` на Keycloak; `GET /auth/callback` ставит HttpOnly cookie.
- `GET /auth/me` → `200 {"authenticated": true, "user": {...}}`; без сессии → `401`.
- `POST /auth/logout` → `204`, сессия помечается revoked, cookie удаляется.
- Мутации (`POST/PATCH/DELETE/PUT`) с cookie требуют заголовок `X-Requested-With: ai-agents-ui` и (если браузер прислал `Origin`) origin из `PUBLIC_URL`; иначе `403`.
- `OIDC is not configured` (`KEYCLOAK_CLIENT_ID`/`SECRET` пусты) → `/auth/login` `503`.

`GET /health` — без auth; `GET /health/db` — `SELECT 1` к PostgreSQL.

## Роли (люди, cookie-сессия)

| Роль | Скоупы | Что может |
|---|---|---|
| `superadmin` | все скоупы | всё + пользователи/роли/лимиты, ключи, настройки LLM |
| `admin` | все кроме `admin` | CRUD и публикация **своих** агентов/скиллов/инструментов, смотреть статистику; без управления доступами и проектных настроек |
| `user` | `agents:read`, `tools:read`, `tools:execute`, `skills:read`, `runs:read`, `runs:execute` | смотреть каталог и запускать агентов/tools; **без** CRUD; **лимит запусков N в сутки** |

- Роль хранится в `user_identities.app_role`; realm-роль из `ADMIN_ROLES` и email из `SUPERADMIN_EMAILS` (по умолчанию `admin@example.com`) дают `superadmin` — список применяется при старте сервиса и при каждом логине.
- **Bootstrap-суперадмин** — аккаунт, чей email входит в `SUPERADMIN_EMAILS`. Только он может **назначать и снимать** суперадминов (`POST/PATCH /api/admin/users` с `app_role=superadmin` или понижение текущего суперадмина). Остальные суперадмины управляют лишь ролями `admin`/`user`; попытка → `403` (`bootstrap-суперадмин ... SUPERADMIN_EMAILS`). Понизить сам bootstrap-аккаунт нельзя (`409`): список всё равно возвращает его в суперадмины при старте и логине. Признаки: `GET /auth/me` → `can_manage_superadmins`, `GET /api/admin/users` → `is_bootstrap`.
- Лимит: `user_identities.daily_run_limit` (если NULL — env `USER_DAILY_RUN_LIMIT`, по умолчанию 20; 0 = без лимита). Считаются запуски за текущие UTC-сутки; сверх лимита `POST /v1/runs` → `429 daily run limit exceeded`.
- Дневной token-бюджет: env `USER_DAILY_TOKEN_LIMIT` (0 = без лимита), только для `app_role=user` и не-суперадминов; суммируются `runs.total_tokens` за текущие UTC-сутки. Исчерпан → `429 daily token budget exceeded`.
- Каталог пользователей: `GET /api/admin/identity-users?q=&limit=` проксирует Keycloak (Keycloak) Admin API через сервисный аккаунт клиента (`client_credentials`); клиенту нужно право realm-management `view-users` (для поиска — ещё `query-users`), иначе `502` с пояснением. Если каталог обслуживает отдельный клиент, задайте `DIRECTORY_ADMIN_CLIENT_ID`/`DIRECTORY_ADMIN_CLIENT_SECRET`. В UI пользователь выбирается из этого списка, а не вписывается вручную.
- Управление: `GET /api/admin/users` (массив), `POST /api/admin/users` `{sub,email?,display_name?,app_role,daily_run_limit?}`, `PATCH /api/admin/users/{sub}` `{app_role?,daily_run_limit?}` — только суперадмин.
- `GET /auth/me` отдаёт `app_role`, `can_manage_superadmins`, `daily_run_limit`; `name` — ФИО (`display_name`) из Keycloak, фолбэк — email.

## Доступ

| Principal | Видит | Правит |
|---|---|---|
| user | свои (любой статус) + `shared`&`published` чужих | только свои |
| service | `shared`&`published`; свои — в `scope=owned` | свои (при `agents:write`) |
| superadmin (`admin` scope / realm-роль `ai-agents-admin`) | всё | всё |

- Запуск: только `status=published` c `published_version_id`; draft → `409 agent is not published`; невидимый агент → `404`.
- Чужие runs: `404` (не `403`).

## Endpoints

| Метод | Path | Доступ |
|---|---|---|
| GET | `/v1/agents?scope=owned\|shared\|all\|archived&stale=skills\|tools\|any&q=&limit=&offset=` | `agents:read` |
| POST | `/v1/agents` | `agents:write` |
| GET | `/v1/agents/{ref}` | `agents:read` |
| PATCH | `/v1/agents/{ref}` | owner/superadmin + `agents:write` |
| DELETE | `/v1/agents/{ref}` | owner/superadmin (архив; повторно — удаление) |
| POST | `/v1/agents/{ref}/publish` | owner/superadmin |
| POST | `/v1/agents/{ref}/clone` | `agents:write` |
| POST | `/v1/agents/{ref}/rollback` | owner/superadmin + `agents:write` |
| GET | `/v1/agents/{ref}/versions` | `agents:read` |
| GET | `/v1/tools` | `tools:read` или `agents:read` |
| GET | `/v1/tools/custom` | `tools:read` или `agents:read` |
| POST | `/v1/tools` | `tools:write` или `agents:write` |
| GET/PATCH | `/v1/tools/{ref}` | `tools:read` / owner+(`tools:write`\|`agents:write`) |
| GET | `/v1/tools/{ref}/usage` | `tools:read` или `agents:read` |
| DELETE | `/v1/tools/{ref}` → `{slug, detached_agents}` | owner/superadmin + `tools:write`\|`agents:write` |
| POST | `/v1/tools/{ref}/test` | `tools:write` или `agents:write` |
| POST | `/v1/tools/{ref}/invoke` | `tools:execute` (+ allowlist service key) |
| GET | `/v1/catalog` | любой из `agents:read` / `tools:read` / `skills:read` (секции по скоупу; DB key — fail-closed allowlist) |
| GET/POST | `/v1/mcp-connections` | `agents:read` / `agents:write` |
| GET/PATCH/DELETE | `/v1/mcp-connections/{ref}` | `agents:read` / owner+`agents:write` |
| POST | `/v1/mcp-connections/{ref}/test` | owner+`agents:write` |
| POST/GET | `/mcp` (Streamable HTTP) | `Authorization: Bearer mcp-ag-…` |
| GET | `/v1/skills` | `skills:read` или `agents:read` |
| GET | `/v1/skills/search?q=` | `skills:read` или `agents:read` (нужен `SKILLS_SH_TOKEN`) |
| POST | `/v1/skills` | `skills:write` или `agents:write` |
| PATCH | `/v1/skills/{ref}` | owner+(`skills:write`\|`agents:write`) |
| POST | `/v1/skills/import` | `skills:write` или `agents:write` |
| POST | `/v1/skills/import-local` | `skills:write` или `agents:write` |
| GET/DELETE | `/v1/skills/{ref}` | `skills:read`\|`agents:read` / owner+(`skills:write`\|`agents:write`) |
| GET | `/v1/settings/llm` | `agents:read` |
| PUT | `/v1/settings/llm` | `admin` (суперадмин) |
| POST | `/v1/settings/llm/models` | `agents:read` |
| POST | `/v1/assist/agent` | `agents:write` |
| POST | `/v1/assist/tool` | `agents:write` |
| POST | `/v1/assist/chat` | `agents:read` (режим `form` — `agents:write`) |
| GET | `/v1/stats/overview?days=14` | `runs:read` |
| GET | `/v1/doctor` | `admin` |
| GET/POST | `/v1/schedules` | `runs:execute` |
| GET/PATCH/DELETE | `/v1/schedules/{id}` | `runs:execute` |
| POST | `/v1/schedules/{id}/run-now` | `runs:execute` |
| POST | `/v1/runs` | `runs:execute` |
| POST | `/v1/runs/preflight` | `runs:execute` |
| GET | `/v1/runs?status=&agent_id=&limit=&offset=` | `runs:read` |
| GET | `/v1/runs/{run_id}` | `runs:read` |
| GET | `/v1/runs/{run_id}/harness` | `runs:read` |
| GET | `/v1/runs/{run_id}/digest` | `runs:read` |
| GET | `/v1/runs/{run_id}/transcript` | `runs:read` |
| GET | `/v1/runs/{run_id}/approvals` | `runs:read` |
| POST | `/v1/runs/{run_id}/approvals/{approval_id}` | `runs:execute` |
| GET | `/v1/runs/compare?left=&right=` | `runs:read` |
| GET | `/v1/runs/{run_id}/events?after=<seq>` | `runs:read` |
| POST | `/v1/runs/{run_id}/cancel` | `runs:execute` |
| GET | `/api/admin/users` (массив) | cookie superadmin |
| POST | `/api/admin/users` | cookie superadmin |
| GET | `/api/admin/identity-users?q=&limit=` | cookie superadmin |
| PATCH | `/api/admin/users/{sub}` | cookie superadmin |
| GET/POST | `/api/admin/service-keys` | cookie superadmin |
| PATCH | `/api/admin/service-keys/{id}` | cookie superadmin (allowlists / scopes) |
| POST | `/api/admin/service-keys/{id}/revoke` | cookie superadmin (enabled=false) |
| DELETE | `/api/admin/service-keys/{id}` | cookie superadmin (hard delete, 204) |
| GET/POST | `/api/admin/notification-channels` | `admin` |
| PATCH/DELETE | `/api/admin/notification-channels/{id}` | `admin` |
| GET | `/api/admin/deliveries?limit=` | `admin` |
| GET/POST | `/api/admin/mcp-servers` | cookie superadmin |
| PATCH/DELETE | `/api/admin/mcp-servers/{ref}` | cookie superadmin |

`ref` — `id` (UUID) или `slug`. `scope` по умолчанию: user → `owned`, service → `shared`; `all` — только superadmin. `shared` — все `visibility=shared` + `status=published` (включая собственные).

## Агент

`POST /v1/agents` (201) / `PATCH /v1/agents/{ref}`:

```json
{
  "slug": "echo-tools",
  "name": "Echo tools",
  "description": "",
  "kind": "preset",
  "plugin_name": null,
  "system_prompt": "Ты калькулятор.",
  "tools": ["calculator", "now"],
  "skills": ["style"],
  "sub_agents": ["child-agent"],
  "memory_enabled": false,
  "llm": {"base_url": null, "model": null, "temperature": 0.2},
  "limits": {"max_steps": 4, "timeout_seconds": 60}
}
```

- `slug` — `^[a-z0-9][a-z0-9-]{1,62}$`, уникален, **неизменяем** после создания (`PATCH` с другим slug → `422`).
- `kind=preset`: обязателен непустой `system_prompt`, `plugin_name` запрещён.
- `kind=plugin`: обязателен `plugin_name`; при создании сразу публикуется версия 1.
- `tools` — только из `GET /v1/tools`; `llm` — только `base_url`/`model`/`temperature` (`api_key` → `422`); `limits` — `max_steps` 1..`MAX_STEPS_CAP`, `timeout_seconds` 1..`RUN_TIMEOUT_CAP_SECONDS`, `max_tokens` 1..`RUN_TOKEN_CAP`, `max_attempts` 1..`RUN_MAX_ATTEMPTS_CAP`, `approval_mode` `never|mutating|all`.
- `memory_enabled` — включить tools `memory_write`, `memory_search`, `memory_delete`; память per-agent/per-principal.
- `kind=preset` — обычный агент: system_prompt + tools/skills + встроенный ReAct; `kind=plugin` — обработчик, зарегистрированный кодом backend (`app/agents/plugins.py`), требует пересборки. Поля prompt/tools/skills/memory у plugin не используются.
- `llm`: пустые `base_url`/`model` → глобальный провайдер приложения; переопределение — дополнительная опция. `temperature` — 0..1 (не проценты), по умолчанию 0.2.
- `sub_agents` — только опубликованные агенты, доступные владельцу (owned/shared), кроме самого агента.
- `limits.approval_mode`: `mutating` — POST/PUT/PATCH/DELETE HTTP и любые MCP tools; `all` — любые tools; `never` — без подтверждения. Ожидание входит в timeout run.
- `limits`/`llm` при `PATCH` заменяются целиком.

Ответ `AgentOut`: `id`, `slug`, `name`, `description`, `kind`, `plugin_name`, `system_prompt`,
`tools`, `skills`, `sub_agents`, `memory_enabled`, `llm`, `limits`, `visibility`, `status`, `published_version`,
`skills_stale`, `tools_stale`, `owner{kind,id,email}`, `created_at`, `updated_at`.
Списки — `{"items": [...], "total": N}`.

- `skills_stale` / `tools_stale` — у published (и archived с `published_version`) тело skill /
  custom-tool в БД отличается от `skill_defs` / `tool_defs` в snapshot текущей published version.
  Draft без публикации → оба `false`. MCP/builtin в `tools_stale` не участвуют.
- Query `stale=skills|tools|any` на `GET /v1/agents` оставляет только агентов с соответствующим флагом.

`POST /v1/agents/{ref}/publish` → `{"visibility": "private"|"shared"}`; создаёт новую версию
(`AgentVersion`, номер = max+1), статус `published`, обновляет `published_version_id`,
снимает `skills_stale`/`tools_stale` (переснимает snapshot).
Запуск: `system_prompt` / `llm` / `limits` / `kind` — из snapshot; **тела skills и tools — live из БД**
по спискам на агенте.
`POST /v1/agents/{ref}/rollback` `{"version": N, "visibility"?: "private"|"shared"}` — берёт снимок версии N,
переносит его поля (name/description/kind/system_prompt/tools/skills/llm/limits) в агента и **публикует новую версию**
(номер max+1); история не переписывается. `visibility` не передан — остаётся прежним. Ссылки на инструменты
проверяются на актуальность: удалённый/выключенный инструмент → `422`. Неизвестная версия → `404`.
`DELETE /v1/agents/{ref}`:
- если агент ещё не в архиве → `200` + тело агента со `status=archived` (запуск запрещён; из `owned`/`shared`/`all` скрыт, виден в `scope=archived`);
- если уже `archived` → `204` безвозвратное удаление (версии CASCADE, runs.agent_id → NULL).
`POST /v1/agents/{ref}/clone` → приватная draft-копия с `slug = <src>-copy-<hex>`.

## Запуск

`POST /v1/runs`:

```json
{
  "agent_id": "echo-tools",
  "input": "17*4+9",
  "llm": {"base_url": "http://host.docker.internal:1234/v1", "model": "local-model"},
  "metadata": {"source": "smoke"}
}
```

- `agent_id` — `id` или `slug`.
- `llm` — per-run override; `api_key` в БД не сохраняется.
- `Idempotency-Key: <[A-Za-z0-9_.:-]{1,128}>` — повтор с тем же ключом и principal возвращает существующий run (`200`, `Idempotency-Replayed: true` при гонке); новый run — `201`. Ключ уникален в паре `(principal_kind, principal_id)`.
- `201` → `RunOut`: `run_id`, `agent_id` (slug), `agent_version`, `harness_hash`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `failure_kind`, `attempts`, `parent_run_id`, `depth`, `events_archived_at`, `status`, `input`, `metadata`, `output`, `error`, `created_at`, `started_at`, `finished_at`.
- `429` — дневная квота запусков, дневной token-бюджет или переполнение очереди (`run queue is full (N)`).

Статусы: `queued | running | waiting_approval | succeeded | failed | cancelled`.

### Sub-agent runs

`limits`/`sub_agents` публикуются в snapshot; tool `call_agent(agent_slug, input)` доступен только
для slug'ов из allowlist. Child run имеет `parent_run_id`, `depth`; выполняется от того же principal,
его usage учитывается в stats и дневных лимитах отдельно. `GET /v1/runs?parent_run_id=<id>` возвращает
дочерние запуски. Лимиты: `RUN_MAX_SUBRUN_DEPTH` (default 2), `RUN_MAX_SUBRUNS_PER_RUN` (default 5);
при превышении tool возвращает `error: subrun ... limit exceeded`. Child runs не занимают отдельный
`RunGate`-слот, пока parent его держит; approvals/retry внутри child работают штатно.

### Skills in the prompt

Полные тела SKILL.md больше не вставляются в system prompt. Вместо этого добавляется индекс
`slug — description` с указанием вызвать `load_skill(slug)`; инструмент доступен только для skills
этого агента и возвращает тело (с лимитом `RUN_TOOL_OUTPUT_MAX_CHARS`). История перед вызовом модели
усекается до `RUN_CONTEXT_MAX_TOKENS` через `pre_model_hook` (`trim_messages`), system message сохраняется.

### Plugin packs

Пакеты — **data-only** манифесты. Два источника:

1. **Из сборки** — `backend/app/plugins/pack_manifests/*.json|*.yaml`, регистрируются при старте;
   меняются только пересборкой backend (immutable в API).
2. **Свои** — создаются админом через `POST /v1/packs` (JSON) или UI `/admin/packs` → «Добавить пакет».
   Хранятся в `custom_packs`, редактируются `PUT`, удаляются `DELETE`; код не исполняют.

Никакого dynamic import/exec: агенты только `preset`, skills/tools — существующие slug'и
(`calculator`, custom HTTP, `mcp:<conn>:<tool>`). Манифест:

```json
{
  "name": "starter",
  "version": "1",
  "description": "...",
  "tools": ["calculator"],
  "skills": [],
  "agents": [
    {"slug": "starter-assistant", "name": "...", "system_prompt": "...", "tools": ["calculator"]}
  ]
}
```

- `GET /v1/packs` — список манифестов + `installed_versions` + `source` (`code|custom`) (superadmin).
- `POST /v1/packs` — создать свой пакет (superadmin); `PUT /v1/packs/{name}` — изменить;
  `DELETE /v1/packs/{name}` — удалить свой пакет (кодовые пакеты → `409`).
- `POST /v1/packs/{name}/install?dry_run=true` — diff `create/update/noop` без записи.
- `POST /v1/packs/{name}/install` — атомарно создаёт/обновляет агентов и публикует их (`shared`),
  затем пишет `pack_installs(name, version)`. Повтор той же версии — `already_installed=true`,
  без новых версий агентов. Новая версия пакета обновляет только агентов с `agents.pack_name=<name>`;
  чужой агент с тем же slug → `409`, без частичных изменений.
- Ошибки ссылок/конфликтов — `409`; неизвестный пакет — `404`.
- Манифесты не содержат секретов; установка не создаёт skills/tools, только ссылается на них.

### Code plugins (kind=plugin)

`kind=plugin` — не пакет и не загрузка файла: это Python-обработчик, зарегистрированный
в `backend/app/agents/plugins.py` через `register_plugin(name, stream)`. Он получает
`system`/`run_override`/`max_steps` и отдаёт `AgentEvent`; prompt/tools/skills/memory
у такого агента не используются. Добавление плагина требует изменения backend и
пересборки образа; из UI можно только указать имя уже зарегистрированного плагина.
Встроенных плагинов в текущей сборке нет.

### Agent memory

При `memory_enabled=true` агенту доступны tools:
`memory_write(key, content, tags?)`, `memory_search(query, limit=5)`, `memory_delete(key)`.
Запись изолирована по `(agent_id, principal_kind, principal_id, namespace=agent_slug)`;
content/tags проходят redaction, content ≤4000. Поиск — SQL `ILIKE` по key/content, только неистёкшие записи.
`expires_at` учитывается при поиске; cleanup не требуется.

- `GET /v1/agents/{ref}/memories` — owner/admin, список текущего principal (superadmin — все).
- `DELETE /v1/agents/{ref}/memories/{memory_id}` — owner/admin.
- UI AgentEditor: toggle «Память агента», таблица записей, удаление.

### Schedules

`/v1/schedules` — cron-расписания запусков; владелец видит только свои, superadmin — все.
`POST` body: `{name, agent_slug, input, cron, timezone, enabled}`; cron — 5 полей, timezone — IANA.
`next_run_at` считается `croniter` в указанной зоне и хранится UTC. Background loop раз в
`RUN_SCHEDULE_POLL_SECONDS` создаёт run от principal создателя с idempotency key
`schedule:<id>:<slot>`; ошибка агента/квоты пишется в `last_error`, loop продолжает работу.
`POST /{id}/run-now` создаёт run немедленно и возвращает `RunOut`.
При недоступном principal (удалён пользователь/отозван ключ) расписание отключается.

| Env | Default | Смысл |
|---|---|---|
| `RUN_SCHEDULE_POLL_SECONDS` | `30` | период проверки due-расписаний |
| `RUN_SCHEDULE_MAX_PER_TICK` | `10` | максимум запусков за тик |
| `RUN_SCHEDULER_ENABLED` | `true` | фоновый scheduler |
| `RUN_DELIVERY_ENABLED` | `true` | фоновый delivery outbox |
| `RUN_MAX_SUBRUN_DEPTH` | `2` | максимальная глубина child runs |
| `RUN_MAX_SUBRUNS_PER_RUN` | `5` | максимум child runs на parent |

### Notifications / delivery outbox

`/api/admin/notification-channels` (scope `admin`):
`{name, kind: webhook|telegram, url?, secret?, chat_id?, enabled}`. Секрет возвращается только как
`secret_configured`; в ответах и логах значения нет.

После терминального run (`succeeded|failed|cancelled`) для каждого enabled-канала создаётся
`deliveries(run_id, channel_id)` (unique). Worker раз в `RUN_DELIVERY_POLL_SECONDS` отправляет:
- webhook JSON `{run_id, agent_id, status, output, error, failure_kind, finished_at}` +
  `X-Ai-Agents-Signature: sha256=<hmac>`, если задан secret;
- Telegram `sendMessage` с текстом (лимит 4000), нужен `TELEGRAM_BOT_TOKEN`.
Ошибки ретраятся с backoff до `RUN_DELIVERY_MAX_ATTEMPTS`, затем `failed`.
`GET /api/admin/deliveries?limit=50` — журнал. Payload не содержит input.

| Env | Default | Смысл |
|---|---|---|
| `RUN_DELIVERY_MAX_ATTEMPTS` | `5` | попыток доставки |
| `RUN_DELIVERY_POLL_SECONDS` | `10` | период outbox |
| `TELEGRAM_BOT_TOKEN` | `""` | токен Telegram-бота |

### Mutating tool approvals

При `limits.approval_mode=mutating` (default) custom HTTP tools с method `POST/PUT/PATCH/DELETE`
и все MCP tools требуют решения человека; `all` — любой tool; `never` — без подтверждений.
Пока решение не принято, run имеет статус `waiting_approval`; слот `RunGate` остаётся занятым.

- `GET /v1/runs/{run_id}/approvals` → `[{id, run_id, tool, input, status, requested_at, resolved_at, resolved_by}]`, `status ∈ pending|approved|rejected|expired`.
- `POST /v1/runs/{run_id}/approvals/{approval_id}` `{"decision":"approve"|"reject"}` — владелец run или superadmin; повторное решение → `409`.
- `RUN_APPROVAL_TIMEOUT_SECONDS` — ожидание входит в общий run timeout; по истечении approval `expired`, run `failed`.
- При рестарте backend pending approvals → `expired`, run → `failed`.
- Plugin-агенты владеют своим runtime и не проходят этот gate; прямые `/v1/tools/...` также вне run.

### GET /v1/runs/{run_id}/harness

Снимок фактически исполненного конфига (для воспроизводимости и диагностики):
`{"run_id", "harness_hash", "snapshot"}`. `harness_hash` — SHA-256 канонического JSON.

`snapshot`: `v`, `agent {slug, version}`, `kind`, `plugin_name`, `system_prompt`, `tools`,
`skills`, `tool_defs` (без значений headers/query/body; только имена и хэш шаблона),
`skill_defs`, `mcp` (только `header_names`), `llm` (без ключа; `api_key_present`),
`limits {max_steps, timeout_seconds, max_tokens, max_attempts, approval_mode}`, `retry {fallback_model}`,
`context {max_tokens, tool_output_max_chars, skills_mode}`, `sub_agents`. Секреты в снимок не попадают.
Версия снапшота: `v=5` для sub-agents; `v=4` (context), `v=3` (approval), `v=2` (retry), `v=1` старые запуски читаются как есть.

Запуски, созданные до появления снимка, отдают `harness_hash=null`; эндпоинт всё равно `200`.

### GET /v1/runs/{run_id}/digest

Сводка траектории из `run_events`; сохраняется в `runs.digest` при завершении run (на лету — только для старых запусков):

- `steps`, `events_total`, `output_chars`, `duration_ms` (`null`, пока запуск не завершён);
- `tool_calls[]` — `{tool, calls, errors}`, где `errors` — результаты с префиксом `error:`;
- `total_tool_calls`, `failed_tool_calls`, `unfinished_tool_calls`;
- `status`, `error`, `agent_version`, `harness_hash`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `failure_kind`, `attempts` (`null`, если провайдер не вернул usage/старый run).

404 — если запуск не существует или не виден вызывающему.

### GET /v1/runs/{run_id}/transcript

`200` → `{"run": RunOut, "digest": TrajectoryDigest, "events": [{seq, event, data, created_at}]}`.
Если события уже удалены retention-задачей (`events_archived_at != null`) → `410 {"detail":"transcript archived"}`;
digest и сам run остаются доступны.

### GET /v1/runs/compare?left=<run_id>&right=<run_id>

Сравнение двух видимых запусков, `200` →
`{"left": RunOut, "right": RunOut, "left_digest": ..., "right_digest": ..., "diff": [...]}`.

`diff[]` — `{field, left, right, changed}` строго для полей:
`agent_version, harness_hash, model, base_url, max_steps, timeout_seconds, max_tokens, max_attempts, fallback_model, approval_mode, context_max_tokens, skills_mode, tools, skills, sub_agents, mcp,
prompt_chars, status, steps, total_tool_calls, failed_tool_calls`.
Для запусков без harness-снимка соответствующие значения `null`.

- `422` — `left == right`; `404` — любой из запусков не найден или не виден.
- Оценка качества ответа не выполняется: только конфиг и агрегаты траектории.
- Роут объявлен до `GET /v1/runs/{run_id}`, поэтому литерал `compare` не трактуется как id.

### GET /v1/doctor

Read-only проверка платформы, scope `admin` (superadmin/cookie или service key с `admin`).
`200 {ok, generated_at, checks[]}`; каждая проверка `{id, status, message, details, duration_ms}`,
`status ∈ ok|warn|error|skip`. `ok=true` только если нет `error`.

Checks: `db`, `migrations`, `llm`, `mcp`, `auth`, `storage`, `queue`, `retention`,
`approvals`, `runs` (failed за 24ч по `failure_kind`). Проверка read-only: approval/события/
MCP-кеш не создаются; MCP и LLM имеют bounded timeout.

### POST /v1/runs/preflight

Проверка готовности опубликованной версии агента **без создания run**:

```json
{"agent_id": "echo-tools", "llm": {"base_url": "...", "model": "..."}}
```

`200` → `{"ok": bool, "checks": [...], "effective": {...}}`.
Каждая проверка: `{id, status, message, details}`; `id` ∈
`agent | plugin | quota | tools | skills | mcp | llm | limits`,
`status` ∈ `ok | warn | error | skip`.

- `ok=true`, только если нет ни одной проверки со `status="error"`; `warn`/`skip` не блокируют.
- `plugin`-агенты проверяют регистрацию плагина; `tools/skills/mcp/llm` для них `skip`.
- `quota` учитывает дневной лимит запусков и (если задан) `USER_DAILY_TOKEN_LIMIT`; сообщение показывает остаток.
- MCP `tools/list` ограничен 12 s; недоступная связь даёт `error`, но остальные проверки выполняются.
- `effective` — `agent_id`, `agent_version`, `model`, `base_url`, `max_steps`, `timeout_seconds`, `max_tokens`, `max_attempts`, `approval_mode`, `tools`, `skills`, `mcp`.
- `404` — агент не найден; `409` — не опубликован; `403` — нет прав.
- Run-строка и события не создаются; кеш MCP не обновляется.

### GET /v1/runs/{run_id}/events?after=<seq> (SSE)

История событий в PostgreSQL (`run_events`) отдаётся сначала, затем live-события до терминального.
`after` — докачка начиная с `seq > after`; `id:` = `seq`.

| event | data |
|---|---|
| `run.started` | `{"agent_id": "...", "agent_version": 1}` |
| `message.delta` | `{"delta": "..."}` |
| `tool.call` | `{"tool": "...", "input": ...}` |
| `tool.result` | `{"tool": "...", "output": "..."}` |
| `agent.step` | `{"node": "..."}` |
| `token.usage` | `{"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10, "model": "..."}` |
| `run.retry` | `{"attempt": 2, "max_attempts": 2, "failure_kind": "transient", "error": "...", "delay_seconds": 1, "model": null}` |
| `run.approval_required` | `{"approval_id": "...", "tool": "...", "input": {...}, "timeout_seconds": 60}` |
| `run.approval_resolved` | `{"approval_id": "...", "decision": "approved|rejected|expired"}` |
| `run.completed` | `{"output": "..."}` |
| `run.failed` | `{"error": "..."}` |
| `run.cancelled` | `{}` |

```bash
curl -N "$BASE/v1/runs/<run_id>/events" -H "Authorization: Bearer $KEY"
```

`POST /v1/runs/{run_id}/cancel` → `cancelled` + `run.cancelled`; идемпотентно.
Для запусков с удалёнными событиями SSE отдаёт одно синтетическое терминальное событие (`seq=1`).
После рестарта backend незавершённые runs переводятся в `failed` (`error="server restarted"`, событие `run.failed`).

## Лимиты

| Env | Default | Смысл |
|---|---|---|
| `RUN_TIMEOUT_SECONDS` | `120` | дефолтный таймаут run |
| `MAX_STEPS` | `8` | дефолтный максимум шагов |
| `MAX_STEPS_CAP` | `32` | верхняя граница для агента |
| `RUN_TIMEOUT_CAP_SECONDS` | `600` | верхняя граница таймаута |
| `RUN_TOKEN_BUDGET` | `200000` | дефолтный per-run token-бюджет |
| `RUN_TOKEN_CAP` | `2000000` | верхняя граница `limits.max_tokens` |
| `RUN_MAX_ATTEMPTS` | `2` | число попыток run по умолчанию |
| `RUN_MAX_ATTEMPTS_CAP` | `5` | верхняя граница `limits.max_attempts` |
| `RUN_RETRY_BACKOFF_SECONDS` | `1` | базовая задержка retry |
| `RUN_RETRY_BACKOFF_MAX_SECONDS` | `8` | потолок задержки retry |
| `RUN_FALLBACK_MODEL` | `""` | модель для повторной попытки (пусто = выключено) |
| `RUN_APPROVAL_MODE` | `mutating` | дефолтный режим подтверждений |
| `RUN_APPROVAL_TIMEOUT_SECONDS` | `60` | ожидание решения по tool |
| `RUN_CONTEXT_MAX_TOKENS` | `24000` | бюджет истории перед вызовом модели |
| `RUN_TOOL_OUTPUT_MAX_CHARS` | `8000` | лимит текста tool result |
| `USER_DAILY_TOKEN_LIMIT` | `0` | дневной token-бюджет user (0 = без лимита) |
| `RUN_MAX_CONCURRENCY` | `4` | одновременно исполняемых runs (одна реплика) |
| `RUN_MAX_CONCURRENCY_PER_AGENT` | `2` | то же на агента |
| `RUN_MAX_QUEUED` | `50` | мягкий cap очереди |
| `RUN_EVENTS_RETENTION_DAYS` | `30` | хранение `run_events`; 0 = выключено |
| `RUN_RETENTION_INTERVAL_SECONDS` | `21600` | интервал retention-цикла |

Фактические значения: `min(agent.limits, cap)`. `agent.step` свыше лимита → `failed` (`max_steps limit exceeded`).
Превышение таймаута → `failed` (`run timed out after Ns`). `token.usage.total_tokens` свыше
`limits.max_tokens` → `failed` (`token budget exceeded (N > M)`); usage пишется только если провайдер его вернул.
Retry выполняется только для `transient`/`rate_limit` и только если в попытке не было `tool.call`;
`timeout` — общий wall-clock и не ретраится. `attempts` и `failure_kind` пишутся в run; между попытками
эмитится `run.retry`, с `RUN_FALLBACK_MODEL` со второй попытки используется fallback-модель.

## Инструменты и навыки (UI)

`/tools` — инструменты, `/skills` — навыки. Отдельные разделы меню (группа «Интеграции»).

- `/tools`: переключатель вида **Плашки / Таблица** (сохраняется в `localStorage`), свои HTTP-инструменты
  и компактные встроенные (имя, число параметров, короткое описание, «Схема параметров» в модалке).
  В таблице: название, источник, метод+URL, число параметров, статус, действия (изменить/проверить/удалить).
- `/skills`: импорт по ссылке, поиск skills.sh, таблица установленных навыков, просмотр SKILL.md и файлов.
- `/runs` принимает `?status=&agent_id=` (синхронизируется с полями фильтра); в детали запуска есть
  **«Повторить»** — создаёт новый ран с тем же агентом и тем же входом.
- `/stats?days=7|14|30&status=succeeded,failed,cancelled` — окно и фильтр статусов графика запусков
  (сумма за период в шапке карточки); параметры живут в URL.
- Бейдж ошибок у «Запуски» показывает только `failed`-раны новее последнего открытия раздела
  (`localStorage: ai-agents.runs-seen-at`), после захода в «Запуски» гаснет.
- `Ctrl/⌘+K` — палитра: разделы, агенты, инструменты, последние запуски.

## Инструменты

`GET /v1/tools` → `[{"name", "description", "parameters", "source"}]`, где `source` = `builtin|custom`.
Встроенные: `get_server_time`, `calculator` (allowlist символов), `now` (IANA tz + алиасы `moscow`/`minsk`/`utc+3`).

### Конструктор без кода (HTTP)

`POST /v1/tools` (201) — кастомный инструмент, `kind=http`:

```json
{
  "slug": "weather",
  "name": "Weather",
  "description": "Прогноз погоды",
  "method": "POST",
  "url": "https://api.example/geo/{city}",
  "headers": {"X-Key": "secret"},
  "query": {"q": "{q}"},
  "body_template": "{\"city\": \"{city}\", \"days\": {days}}",
  "content_type": "application/json",
  "parameters": [
    {"name": "city", "type": "string", "required": true},
    {"name": "q", "type": "string", "required": true},
    {"name": "days", "type": "integer", "required": false}
  ],
  "timeout_seconds": 20,
  "enabled": true
}
```

- `{param}` в `url` подставляется URL-экранированным; в `query`/`headers` — как есть; в `body_template` строковые значения JSON-экранируются (внутри кавычек), числовые/boolean — как raw JSON.
- `parameters[].type`: `string|number|integer|boolean`; `enum` опционален; `required` по умолчанию `true`.
- `timeout_seconds` 1..60, ответ обрезается до 8000 символов, HTTP ≥400 и сетевые ошибки возвращаются агенту текстом `error: …`.
- `headers` хранятся в БД как есть и **не возвращаются** API: в ответе только `header_names`.
  `PATCH headers` заменяет словарь целиком; отсутствие поля — не менять.
- URL: только `http(s)`; запрещены loopback/private/link-local/metadata и credentials в URL
  (SSRF-guard). Redirects при вызове не следуются. Host с `{placeholders}` запрещён.
- `GET /v1/tools/custom` — свои инструменты (owner, enabled, method, url, `header_names`); `PATCH` — точечно и сразу действует на следующие запуски; `DELETE` — удаляет инструмент и отвязывает его от агентов (`{slug, detached_agents}`).
- `POST /v1/tools/{ref}/test` `{"params": {...}}` → `{"ok": bool, "status": int|null, "output": "..."}`.
- Имя инструмента в `agents.tools` = `slug`; встроенные имена заняты. Удалённый/выключенный инструмент нельзя привязать или переопубликовать агента (`422`).
- **Инструменты и навыки применяются вживую**: правка custom-инструмента (`PATCH /v1/tools/{ref}`)
  или навыка (`PATCH /v1/skills/{ref}`) действует на следующий запуск без перепубликации —
  определения резолвятся из БД на старте рана. Списки `tools`/`skills` — с текущей записи агента.
  Snapshot `tool_defs`/`skill_defs` при publish остаётся для истории/rollback; UI показывает
  `tools_stale`/`skills_stale`, пока live ≠ snapshot.
- Системный промпт, LLM и limits по-прежнему из снимка опубликованной версии (нужен `publish`).
- `GET /v1/tools/{ref}/usage` → `{slug, total, agents: [{slug, name, status, published_version}]}` — кем используется.
- `DELETE /v1/tools/{ref}` возвращает `{slug, detached_agents: [slug]}`: инструмент удаляется и **автоматически отвязывается от всех агентов**, которые на него ссылались (UI показывает это предупреждение до удаления).
- Ответ инструмента уходит в контекст модели (обрезается до 8000 символов): для локальных моделей с малым окном запрашивайте компактный ответ (минимум полей, 1–2 дня), иначе ран падает с `exceeds the available context size`.

## Каталог и invoke (гибрид для оркестраторов)

Для «умных» клиентов (фабрика): мозг у клиента, ai-agents отдаёт каталог и исполнители.

- `GET /v1/catalog` → `{agents: [{slug,name,description}], tools: [ToolSpec…], skills: [{slug,name,description}]}`.
  Секция отдаётся только при соответствующем `*:read`. Skills **без** полного `content`
  (его даёт `GET /v1/skills/{ref}` + `skills:read`).
- DB service key: поля `agent_slugs` / `tool_slugs` / `skill_slugs` — **fail-closed** (пустой список
  категории → пустой массив в catalog). Env `SERVICE_API_KEYS` и cookie-пользователи —
  без ограничения catalog.
- `POST /v1/tools/{ref}/invoke` `{params}` → `{ok, output}`: builtin или enabled custom, **без**
  `create_run` / LLM. Нужен scope `tools:execute` (не `tools:write`); для DB service key slug
  должен быть в `tool_slugs`.
- `GET /v1/skills/{ref}` при DB service key — только slug из `skill_slugs` (иначе `404`).
- Эксперты для фабрики: канон `POST /v1/runs` + SSE (`runs:execute`), модель — из `llm` агента.

## MCP (наружу)

Проект сам является MCP-сервером (Streamable HTTP, официальный SDK `mcp` 2.x). Allowlist на ключе
(`agent_slugs`, `tool_slugs`, `skill_slugs`) задаёт состав `tools/list` по категориям независимо
(пустой список категории → эта категория не отдаётся).

- Endpoint один на инсталляцию: `POST {PUBLIC_URL}/mcp` (+ `GET` для SSE-потока). UI-страница
  управления живёт по `/integrations/mcp` — путь `/mcp` занят endpoint'ом (nginx проксирует его в backend). Разные
  «MCP-серверы» в UI = разные Bearer-ключи/метки, не разные пути.
- Авторизация: `Authorization: Bearer mcp-ag-…`; ключ создаётся суперадмином в UI
  (`/integrations/mcp` → «Серверы», форма редактирования: JSON-конфиг + «Новый ключ»)
  или через `/api/admin/mcp-servers`. Хранится только sha256-хеш, показывается один раз;
  `PATCH {"rotate_key": true}` выдаёт новый и отзывает старый;
  `PATCH {"enabled": false}` выключает ключ без удаления.
  `agent_slugs` — только published+shared; `tool_slugs` — builtin/enabled custom;
  `skill_slugs` — существующие skills; иначе create/update → `422`.
- `tools/list`:
  - агенты: `name` = slug, arg `prompt` (без смены имён — совместимость IDE);
  - atomic tools: `name` = `tool__{slug}`, schema из parameters, call = invoke **без** LLM;
  - при непустом `skill_slugs` — tool `get_skill` с arg `slug` → текст SKILL.md.
- `tools/call` агента → `POST /v1/runs` от имени `principal.kind="mcp"` (`principal_id` = slug
  ключа, в `runs.metadata.mcp_server` тот же slug). Ответ — **финальный текст рана**
  (`runs.output`); пустой/незавершённый/`failed` ран → `isError: true` с текстом ошибки.
  Неизвестный агент → `isError: true, "error: unknown agent: …"`; отсутствующий `prompt` →
  `"error: prompt is required"`; превышение `RUN_TIMEOUT_CAP_SECONDS + 30` → ран отменяется,
  `"error: run timed out"`.
- `/.well-known/oauth-protected-resource/mcp` — RFC 9728 метаданные ресурса (клиенты
  показывают их в ошибках авторизации; полноценного OAuth-флоу нет — только статический ключ).
- Защита от DNS-rebinding включена: допустимы `Host` из `PUBLIC_URL` и `localhost`/`127.0.0.1`
  (с любым портом). Запрос с другим `Host` (например, именем compose-сервиса изнутри сети)
  получает `421 Invalid Host header`.

Пример конфига клиента (Cursor / Claude Desktop / Claude Code):

```json
{"mcpServers": {"ai-agents": {"url": "https://ai-agents-dev.example.com/mcp",
  "headers": {"Authorization": "Bearer mcp-ag-…"}}}}
```

| Метод | Path | Тело / ответ |
|---|---|---|
| GET | `/api/admin/mcp-servers` | `{items: [{…, agent_slugs, tool_slugs, skill_slugs, url}], total}` — без ключей |
| POST | `/api/admin/mcp-servers` | `{slug, name, description, agent_slugs?, tool_slugs?, skill_slugs?}` → `201` + `api_key` |
| PATCH | `/api/admin/mcp-servers/{ref}` | `{name?, description?, enabled?, agent_slugs?, tool_slugs?, skill_slugs?, rotate_key?}` |
| DELETE | `/api/admin/mcp-servers/{ref}` | `204` / `404` |

## MCP-подключения (внутрь)

Обратное направление: агент использует инструменты **внешних** MCP-серверов.
Транспорт — только Streamable HTTP (`url`); stdio не поддерживается (запуск произвольного
процесса в backend — RCE-поверхность), SSE в SDK 2.x superseded.

`POST /v1/mcp-connections` (201):

```json
{
  "slug": "internal-docs",
  "name": "Internal docs",
  "description": "Корпоративный поиск",
  "url": "https://mcp.example.com/mcp",
  "headers": {"Authorization": "Bearer secret"},
  "timeout_seconds": 30,
  "enabled": true
}
```

- `headers` хранятся в БД как есть и **не возвращаются** API: в ответе только `header_names`.
  `PATCH headers` заменяет словарь целиком; отсутствие поля — не менять.
- URL подчиняется тому же SSRF-guard, что и custom tools (private/metadata запрещены; DNS
  проверяется при probe/вызове). Исключение — явный allowlist приватных MCP-целей
  `MCP_EGRESS_ALLOWED_HOSTS` (host, `*.suffix`, IP/CIDR через запятую/пробел); действует
  только на MCP-подключения, custom tools остаются public-only.
- `timeout_seconds` 1..120 — таймаут одного вызова инструмента.
- Инструмент в `agents.tools` записывается как `mcp:<connection-slug>:<tool>`
  (`^mcp:[a-z0-9][a-z0-9-]{1,62}:[A-Za-z0-9_.-]{1,128}$`).
- Сохранение агента (`POST/PATCH /v1/agents`, rollback) проверяет каждый `mcp:`-ref:
  формат, существование подключения, `enabled`, право редактирования (владелец или
  superadmin). Неизвестное/выключенное подключение → `422`, чужое → `403`.
- Запуск: подключение резолвится **в момент старта рана**; недоступность/удаление/выключение
  → ран `failed` с текстом ошибки. MCP-сессия живёт весь запуск и закрывается по его
  завершении; имя инструмента в событиях рана — `mcp_<connection>_<tool>` (санитизация до
  `[A-Za-z0-9_-]`, ≤64 символов), ответ обрезается до 8000 символов.
- `POST /v1/mcp-connections/{ref}/test` → `{ok, tools: [{name, description}], error}` и
  обновляет кеш `tools_cache`/`tools_cached_at` (UI показывает список инструментов в
  редакторе агента).
- `DELETE /v1/mcp-connections/{ref}` → `{slug, detached_agents}`: подключение удаляется и
  все `mcp:<slug>:*` вычищаются из `agents.tools`.

## Настройки LLM (проектные)

Провайдеры — именованные OpenAI-compatible записи (`llm_providers`): имя, `base_url`, `api_key`, `model`.
Один провайдер назначается активным (`app_settings.active_llm_provider_id`).

Приоритет для запусков и AI-автозаполнения: `llm` ран-а → `agent.llm` → **активный провайдер** → legacy-поля `app_settings` → env (`DEFAULT_LLM_*`).

| Метод | Path | Тело / ответ |
|---|---|---|
| GET | `/v1/settings/llm/providers` | `{items, active_id, effective}`; `agents:read` |
| POST | `/v1/settings/llm/providers` | `{name, base_url, model?, api_key?, auth_type?, auth_header?, auth_prefix?}` → провайдер; имя уникально (`409`); `admin` |
| PATCH | `/v1/settings/llm/providers/{id}` | `{name?, base_url?, model?, api_key?, auth_type?, auth_header?, auth_prefix?, clear_api_key?}`; `admin` |
| DELETE | `/v1/settings/llm/providers/{id}` | `{deleted, active_id}`; удаление активного снимает указатель; `admin` |
| PUT | `/v1/settings/llm/active` | `{provider_id: id \| null}` → `{items, active_id, effective}`; `admin` |
| POST | `/v1/settings/llm/models` | `{base_url?, api_key?, auth_type?, auth_header?, auth_prefix?}` → `{base_url, models: [id]}`; пустые поля берутся из активного провайдера; `agents:read` |
| GET/PUT | `/v1/settings/llm` | legacy: эффективная конфигурация и запись legacy-полей (используются, только если активный провайдер не задан) |

### Схема авторизации провайдера

Не все шлюзы ждут `Authorization: Bearer <ключ>`, поэтому она настраивается:

| `auth_type` | Что уходит в запросе |
|---|---|
| `bearer` (по умолчанию) | `<auth_header>: <auth_prefix><ключ>`; по умолчанию `Authorization: Bearer <ключ>` |
| `header` | тот же шаблон без подразумеваемого префикса: например `x-api-key: <ключ>` (`auth_prefix: ""`) |
| `none` | заголовка авторизации нет (локальные LM Studio / Ollama) |

- `auth_header` — имя HTTP-заголовка (`^[A-Za-z0-9][A-Za-z0-9-]{0,63}$`, по умолчанию `Authorization`), `auth_prefix` — строка перед ключом (по умолчанию `Bearer `, может быть пустой), до 32 символов.
- Заголовок подставляется и в `ChatOpenAI` (`default_headers`, перекрывает `Authorization` SDK), и в пробу `POST /v1/settings/llm/models`.
- В UI (`/settings`) есть пресеты — OpenAI-совместимый, LM Studio, Ollama, Anthropic-совместимый шлюз — они лишь заполняют `base_url` и схему авторизации, все поля остаются редактируемыми. Транспорт всегда OpenAI-compatible (`/v1/chat/completions`, `/v1/models`): для «anthropic-совместимого» нужен шлюз, транслирующий OpenAI API.
- Незаполненные поля провайдера (например, пустой `api_key` локального LM Studio) берутся из env `DEFAULT_LLM_API_KEY` — иначе сервер ответит 401.
- Провайдеры и активный указатель — только `admin` (cookie-суперадмин или сервисный ключ со скоупом `admin`).
- `api_key` наружу не отдаётся: в ответах `api_key_set` + `api_key_hint` (последние 4 символа); пустое поле при `PATCH` — «не менять», `clear_api_key: true` — удалить.
- Кэш процесса обновляется при старте и после каждой мутации, поэтому новые запуски сразу идут на актуальный эндпоинт.
- Миграция `007_llm_providers` превращает существующие legacy-настройки в провайдера `default` и делает его активным; `010_llm_auth` добавляет `auth_type/auth_header/auth_prefix` (старые строки — `bearer`/`Authorization`/`Bearer `).

```bash
curl -X POST "$BASE/v1/settings/llm/providers" -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"lm-studio","base_url":"http://host.docker.internal:1234/v1","model":"qwen3.5-4b"}'
curl -X PUT "$BASE/v1/settings/llm/active" -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" -d '{"provider_id":"<uuid>"}'
```

## ИИ-ассистент (чат по всему сервису)

Кнопка «AI» в правом нижнем углу любой страницы открывает боковую панель. Модель — **активный
LLM-провайдер** (тот же, что у тестовых запусков), включая настроенную схему авторизации.

`POST /v1/assist/chat` (`agents:read`; режим `form` — ещё `agents:write`):

```json
{
  "mode": "form",                  // form | advice | review | test
  "target": "agent",               // agent | tool | llm | mcp-connection | mcp-server | skill | user | service-keys | general
  "message": "агент для прогноза погоды по Example",
  "current": {"name": "старое"},   // текущие значения формы (контекст)
  "history": [{"role": "user", "content": "…"}]
}
```

→ `{"answer": "текст по-русски", "fields": {...} | null, "warnings": ["…"]}`

- В `fields` допускается строка `page_search` — подстрока для поля поиска на странице со списком
  (агенты, инструменты, навыки, MCP, пользователи, LLM-провайдеры, сервисные ключи, запуски, обзор,
  документация и др.); остальные ключи фильтруются по белому списку для выбранного `target`.

- Режимы: `form` — сгенерировать значения полей (кнопка «Применить к форме» заполняет открытую
  форму), `advice` — как сделать шаг в сервисе, `review` — разобрать текущую конфигурацию,
  `test` — предложить проверку (промпт, ожидаемые события запуска).
- `fields` фильтруются по белому списку полей формы и приводятся к нужным типам; секреты
  (`api_key`, токены) не генерируются — в ответе только `warnings`.
- `tools`/`skills`/`agent_slugs`/`tool_slugs`/`skill_slugs` в ответе — только имена из реального
  каталога; в промпт попадает **карта сервиса с краткими описаниями** (инструменты, навыки,
  агенты, MCP-подключения/серверы, маршруты UI), чтобы ассистент мог искать «что есть на странице».
- Заполнение форм (`form` + «Применить»): список агентов (→ `/agents/new`), редактор агента,
  конструктор инструмента, навыки (`/skills`), LLM-провайдер, MCP-подключение/сервер (в т.ч.
  allowlist `*_slugs`), карточка пользователя. На страницах без формы (runs/stats/docs…) target
  `general`, режим `form` недоступен — остаются advice/review/test по каталогу.

## AI-автозаполнение форм

Подсказчики не пишут в БД: LLM видит реальный каталог `GET /v1/tools` и импортированные скиллы,
а ответ нормализуется (несуществующие имена отбрасываются и попадают в `warnings`).

`POST /v1/assist/agent` `{"description": "агент-калькулятор с подсказкой времени"}` →
```json
{"name":"…","slug":"…","description":"…","system_prompt":"…",
 "tools":["calculator"],"skills":["frontend-design"],
 "new_tools":[{"slug":"weather","name":"…","description":"…","note":"какой API подключить"}],
 "notes":"что уточнить у пользователя","warnings":["инструмент «x» не найден — пропущен"]}
```

`POST /v1/assist/tool` `{"description": "прогноз погоды по городу"}` →
`{slug, name, description, method, url, headers, query, body_template, content_type, parameters[], notes, warnings}`.

- `slug` санитизируется (`^[a-z0-9][a-z0-9-]{1,62}$`, кириллица транслитерируется), занятые slug получают суффикс.
- `tools`/`skills` — только существующие имена; `new_tools` не дублирует доступные.
- `method`/`type`/`name` параметров валидируются, некорректные значения отбрасываются с предупреждением.
- Значения заголовков-секретов LLM не придумывает (пустая строка) — их заполняет человек.
- LLM недоступна или вернула не JSON → `502`.

## Статистика использования

Собирается внутри сервиса, внешний стек (ClickHouse/MinIO) не нужен:

- **запуски** — из таблицы `runs` (статус, агент, длительность);
- **вызовы инструментов** — `usage_events(kind='tool')`, пишется на каждом событии `tool.call` (slug инструмента, агент, run, principal);
- **API-запросы** — `usage_events(kind='api')`: ASGI-middleware фиксирует метод, путь, код ответа, длительность и principal (для SSE длительность = вся жизнь стрима). Служебные пути (`/health`, `/docs`, `/openapi.json`, `/redoc`, `OPTIONS`) не пишутся.
- Запись асинхронная (fire-and-forget): сбой аналитики не влияет на запрос/ран. Хранение — 180 дней, чистка при старте.

`GET /v1/stats/overview?days=7|14|30` (1..90) → всё для графиков одним ответом:

```json
{
  "days": 14, "since": "2026-10-22T00:00:00Z",
  "runs_total": 42, "runs_succeeded": 39, "success_rate": 0.929,
  "runs_daily": [{"date": "2026-11-04", "succeeded": 3, "failed": 0, "cancelled": 0, "other": 0}],
  "tokens_total": 128000, "queued_runs": 2, "oldest_queued_seconds": 14,
  "tools_total": 128, "tools_daily": [{"date": "2026-11-04", "calls": 12}],
  "api_total": 530, "api_errors": 7,
  "api_latency": {"p50_ms": 12, "p95_ms": 84},
  "api_daily": [{"date": "2026-11-04", "calls": 61, "errors": 1}],
  "top_agents": [{"slug": "calc", "runs": 12, "succeeded": 11, "failed": 1, "success_rate": 0.917, "avg_duration_ms": 2400, "tokens": 42000}],
  "top_tools": [{"slug": "calculator", "calls": 31}],
  "top_endpoints": [{"method": "GET", "path": "/v1/agents", "calls": 44, "errors": 0, "p95_ms": 18}]
}
```

UI: страница «Обзор» (`/stats`, `@mantine/charts`) — карточки, запуски по дням, API-запросы/ошибки, вызовы инструментов, топ агентов и эндпоинтов.

## Скиллы (skills.sh)

Скиллы — процедурные инструкции (SKILL.md), которые добавляются к system prompt агента.

Свой навык (без импорта): `POST /v1/skills` `{name, slug?, description?, content}` — `source=manual`, slug выводится транслитерацией из названия; дубль slug → `409`. `PATCH /v1/skills/{ref}` меняет `name/description/content` только у `manual` (импортированный → `409`, редактируется повторным импортом).

Генерация SKILL.md ассистентом: `POST /v1/assist/skill` `{description}` → `{name, slug, description, content, notes, warnings}`; бэкенд добавляет YAML frontmatter шаблона skills.sh, если модель его пропустила, и санитизирует slug.

`POST /v1/skills/import` `{"url": "https://skills.sh/<owner>/<repo>/<skill>"}`:

- GitHub-backed источники (`id` вида `owner/repo/skill`); забирается `SKILL.md` (+ до 25 файлов папки) через GitHub (или официальный API skills.sh, если задан `SKILLS_SH_TOKEN`).
- Повторный импорт того же `source_id` обновляет контент (по hash), не создавая дубль.
- `GET /v1/skills` / `GET /v1/skills/{slug}` (content + files) / `DELETE`.
- `GET /v1/skills/search?q=` проксирует skills.sh; без `SKILLS_SH_TOKEN` → `503` (используйте импорт по URL).

Локальный импорт: `POST /v1/skills/import-local` — ровно одно из полей:

- `{"entries": [{"path": "my-skill/SKILL.md", "content": "---\\n…"}, …]}` — **основной способ из UI**: браузер читает файл/папку на машине пользователя и шлёт содержимое (не путь Windows/Linux на сервер).
- `{"path": "/data/skills"}` — опционально для ops/API: путь **как видит backend** (файл `.md` / `SKILL.md` или папка). Только внутри `STORAGE_PATH` (по умолчанию `/data`) или `SKILLS_IMPORT_ROOTS`. В Compose смонтируйте каталог в `/data/…`.

Ответ: `{items, created, updated, skipped[]}`. `source=local`; повтор по тому же `source_id` обновляет контент.

Привязка: `agents.skills: ["frontend-design"]`. При публикации тела скиллов и custom-tools
записываются в `agent_versions.snapshot.skill_defs` / `tool_defs` (аудит/история/rollback).
Запуск резолвит skills и tools **live из БД**; правка навыка или custom-tool действует без
перепубликации, но выставляет `skills_stale` / `tools_stale` до следующего publish.
Промпт: system prompt (из snapshot) + «# Skills (procedural knowledge)» + live-тела SKILL.md.

Переменные (secrets): `GITHUB_TOKEN` (поднять лимит GitHub API), `SKILLS_SH_TOKEN` (Vercel OIDC для официального API).

## Ошибки

| Код | Причина |
|---|---|
| 401 | нет/неверный Bearer, нет cookie-сессии |
| 403 | нет скоупа, не owner, нет CSRF-заголовка |
| 404 | агент/run не найден или невидим |
| 409 | агент не опубликован / slug занят |
| 422 | невалидное тело, неизменяемый slug |
| 503 | service auth не сконфигурирован / OIDC выключен |

## Smoke (curl)

```bash
BASE=http://localhost:8096
KEY=change-me

# 1) Создать и опубликовать preset-агента
curl -s -X POST "$BASE/v1/agents" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"slug":"smoke-calc","name":"Smoke","system_prompt":"Ты калькулятор.","tools":["calculator"]}'
curl -s -X POST "$BASE/v1/agents/smoke-calc/publish" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"visibility":"shared"}'

# 2) Запуск
RUN_ID=$(curl -s -X POST "$BASE/v1/runs" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"agent_id":"smoke-calc","input":"17*4+9"}' \
  | sed -E 's/.*"run_id":"([^"]+)".*/\1/')

curl -sN "$BASE/v1/runs/$RUN_ID/events" -H "Authorization: Bearer $KEY"
curl -s "$BASE/v1/runs/$RUN_ID" -H "Authorization: Bearer $KEY"
```

Ожидаемо: `run.started` → `tool.call(calculator)` → `tool.result(77)` → `run.completed`, статус `succeeded`.

MCP-сервер (нужен cookie-суперадмин → `POST /api/admin/mcp-servers`, ключ `mcp-ag-…`):

```bash
curl -s -X POST "$BASE/mcp" -H "Authorization: Bearer mcp-ag-…" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}'
# 200/202 — ключ принят; 401 — ключ неверный/отозван/выключен

curl -s "$BASE/.well-known/oauth-protected-resource/mcp"
```

MCP-клиент (подключение к внешнему серверу): `POST /v1/mcp-connections` → `POST /v1/mcp-connections/<slug>/test` → агенту в `tools` записать `mcp:<slug>:<tool>`.

## База данных

PostgreSQL — **на хосте**, не в Compose. `alembic upgrade head` сам создаёт БД (если нет)
и накатывает только недостающие миграции; в Compose это контейнер `ai-agents-migrate`,
в k8s — initContainer `migrate-db`. DDL в lifespan не выполняется.

## Lab / локальный Keycloak

`docker-compose.lab.yml` направляет OIDC в локальный `keycloak-dev`
(`extra_hosts: keycloak.example.com:host-gateway`); issuer у lab и work один —
`https://keycloak.example.com/realms/ai-agents` (его объявляет `KC_HOSTNAME_URL` локального KC).
