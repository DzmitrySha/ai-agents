# LangGraph: минимальное внедрение (4 этапа)

## Context

Задача — взять из статьи только то, что реально усиливает наш control plane, не меняя архитектуру. У нас уже есть свой FastAPI-фасад, SSE-стриминг токенов, runs/events в Postgres, approvals, расписания, субагенты, память, MCP и Langfuse. Поэтому принимаются четыре точечные доработки: (1) Studio как dev-инструмент визуальной отладки графа, (2) прокидывание `extra_body` (отключение thinking у локальных моделей), (3) метрика «веса» tool-схем в запуске, (4) opt-in Postgres-чекпоинтер для восстановления/реплея. LangGraph Server как отдельный рантайм и LangSmith в план не входят: это дублировало бы наш API и добавило бы ещё два stateful-сервиса.

## Порядок и зависимости

- Этап 1 (Studio) независим, prod-кода не касается.
- Этап 2 (`extra_body`) независим.
- Этап 3 (`tools.schema`) независим, но меняет `stream_agent`; выполнять до этапа 4, чтобы не конфликтовать по одному файлу.
- Этап 4 (чекпоинтер) — после 3, по умолчанию выключен (`LANGGRAPH_CHECKPOINT_ENABLED=false`).

---

## Этап 1. LangGraph Studio (только dev)

Цель: видеть узлы ReAct-цикла, state и историю чекпоинтов без прод-сервера. Studio поднимает `langgraph dev` с in-memory чекпоинтером; наш обычный образ и прод-деплой не меняются.

1. `backend/pyproject.toml`: в `[project.optional-dependencies]` добавить отдельный extra (не в `dev`, чтобы не утяжелять CI):
   ```toml
   studio = ["langgraph-cli[inmem]"]
   ```

2. Создать `backend/langgraph.json`:
   ```json
   {
     "dependencies": ["."],
     "graphs": {"dev_agent": "./studio/graph.py:graph"},
     "python_version": "3.12"
   }
   ```
   Ключ `env` не задавать: настройки читаются `app.settings` (`../docker/.env`, `../docker/.env.secrets`, env процесса).

3. Создать `backend/studio/graph.py` — модуль обязан импортироваться без БД и без сети:
   - путь к снимку агента: `os.environ.get("STUDIO_AGENT")`, иначе `studio/agent.json`, иначе `studio/agent.example.json`; если файла нет — `RuntimeError(f"studio agent snapshot not found: {path}")`;
   - JSON-схема снимка: `{"system_prompt": str (обязателен), "tools": [str], "tool_defs": [dict], "skills": [{"slug","name","content"}], "llm": {"model","base_url","temperature"}}`;
   - сборка инструментов: импортировать и вызвать существующий `app.agents.execution._agent_tools(tools, tool_defs)` (не переименовывать: он используется в `backend/tests/test_run_approvals.py`);
   - промпт: существующий `app.agents.execution.compose_prompt(system_prompt, skills)`;
   - LLM: существующий `app.agents.execution.build_llm(llm, None)`;
   - итог: `graph = create_react_agent(build_llm(...), tools=tools, prompt=compose_prompt(...))` (`create_react_agent` уже импортируется в `execution.py`);
   - любой `RuntimeError` из `_agent_tools` перехватывать и перевыбрасывать как `RuntimeError(f"{path}: {exc}")`;
   - Studio-снимок не поддерживает MCP-подключения, субагентов, память, approvals и `load_skill` — это явное ограничение dev-режима, не дописывать их.

4. Создать `backend/studio/agent.example.json` — минимальный рабочий снимок с `"tools": ["get_server_time"]`, пустыми `skills`/`tool_defs`, LLM из env (`"llm": {}`).

5. `.gitignore`: добавить строку `backend/studio/agent.json` (личный снимок не коммитим; example — коммитим).

6. Создать `backend/studio/README.md`: команда запуска, формат снимка, ограничения.

Запуск и проверка — в разделе Verification (этап 1).

---

## Этап 2. `extra_body` у LLM-провайдера

Цель: на work-контуре отправлять локальной модели параметры вида `{"chat_template_kwargs": {"enable_thinking": false}}` без правок кода и пересборки.

1. `backend/app/models.py`, класс `LLMProvider`: добавить колонку
   ```python
   extra_body: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
   ```
   (`JSON` уже импортирован в модуле).

2. Новая миграция `backend/alembic/versions/024_provider_extra_body.py`:
   - `revision = "024_provider_extra_body"`, `down_revision = "023_custom_packs"`;
   - `upgrade`: `op.add_column("llm_providers", sa.Column("extra_body", sa.JSON(), nullable=True))`;
   - `downgrade`: `op.drop_column("llm_providers", "extra_body")`.

3. `backend/app/runtime/models.py`:
   - `LLMConfig`: поле `extra_body: dict[str, Any] | None = None`;
   - `LLMProviderCreate`: `extra_body: dict[str, Any] | None = None` + validator `_extra_body`: если значение не `None` и `len(json.dumps(value, ensure_ascii=False)) > 4096` → `ValueError("extra_body must be <= 4096 chars")`;
   - `LLMProviderUpdate`: `extra_body: dict[str, Any] | None = None` и `clear_extra_body: bool = False` (семантика как у `clear_api_key`: отсутствие поля/`None` — не менять, `clear_extra_body: true` — обнулить);
   - `LLMProviderOut`: `extra_body: dict[str, Any] | None = None`.

4. `backend/app/repos/llm_providers.py`: `to_out` отдаёт `extra_body`; `create_provider` пишет `data.extra_body`; `update_provider` — `if data.clear_extra_body: provider.extra_body = None; elif data.extra_body is not None: provider.extra_body = data.extra_body`.

5. `backend/app/repos/project_settings.py`, ветка активного провайдера в `resolve()`: добавить `extra_body=provider.extra_body` в `LLMConfig(...)`. Ветки legacy/env оставить без поля (`None`).

6. `backend/app/agents/execution.py`:
   - `resolve_llm()` возвращает `"extra_body": override.extra_body if override.extra_body is not None else project.extra_body`;
   - `build_llm()` передаёт `extra_body=resolved["extra_body"]` в `ChatOpenAI(...)`.
   Приоритет как у остальных полей: `llm` ран-а → провайдер/project → нет.

7. Frontend:
   - `frontend/src/types.ts`, `LLMProvider`: `extra_body: Record<string, unknown> | null;`
   - `frontend/src/pages/SettingsPage.tsx`, `ProviderCard`: состояние `extraBody` (строка, initial `provider.extra_body ? JSON.stringify(provider.extra_body, null, 2) : ""`), поле `Textarea` с label `t("llmSettings.extraBody")`, description `t("llmSettings.extraBodyHint")`; на сохранении — `JSON.parse`, при ошибке `onError(t("llmSettings.extraBodyInvalid"))` и не отправлять; в PATCH отправлять `{"extra_body": parsed}` при непустом поле и `{"clear_extra_body": true}` при очистке;
   - i18n `frontend/src/i18n/locales/ru.ts` и `en.ts`, секция `llmSettings`: ключи `extraBody`, `extraBodyHint`, `extraBodyInvalid`.

8. `docs/API.md`, раздел «Настройки LLM (проектные)» и «Схема авторизации провайдера»: добавить `extra_body` в тела POST/PATCH и в описание, пример `{"extra_body": {"chat_template_kwargs": {"enable_thinking": false}}}` и пометку, что объект уходит в `ChatOpenAI(extra_body=...)` как есть.

9. Тесты:
   - `backend/tests/test_llm_providers.py`: создать провайдера с `extra_body`, проверить его в ответе, проверить PATCH и `clear_extra_body`, проверить 422 на `extra_body` > 4096 символов;
   - `backend/tests/test_llm_auth.py`: новый тест — `llm_config.set_cached(LLMConfig(base_url=..., model=..., extra_body={"chat_template_kwargs": {"enable_thinking": False}}))`, замокать `app.agents.execution.ChatOpenAI` и проверить, что `build_llm({}, None)` вызван с этим `extra_body`.

---

## Этап 3. Метрика tool-схем (`tools.schema`)

Цель: видеть, сколько контекста съедают JSON-схемы инструментов конкретного запуска, и предупреждать в редакторе агента.

1. `backend/app/agents/execution.py`, `stream_agent()`: после полной сборки `tools` (после блока memory-инструментов, перед `create_react_agent`) добавить первый yield:
   ```python
   import json  # добавить в шапку модуля

   schema = json.dumps(
       [t.args_schema.model_json_schema() for t in tools],
       ensure_ascii=False,
       separators=(",", ":"),
   )
   yield AgentEvent(
       "tools.schema",
       {
           "count": len(tools),
           "approx_tokens": len(schema) // 4,
           "names": [t.name for t in tools],
       },
   )
   ```
   Событие эмитится только для `kind="preset"`: ветка `plugin` выходит раньше и остаётся без него.

2. `frontend/src/types.ts`, union `RunEventName`: добавить `| "tools.schema"` (severity/обработка не нужна: журнал событий в RunDetail рендерится по строке имени).

3. `docs/API.md`, таблица событий SSE: строка
   `| tools.schema | {"count": 7, "approx_tokens": 812, "names": ["now", ...]} |`.

4. `backend/tests/test_execution.py`:
   - обновить ожидаемый список в `test_graph_events_are_translated` — первым элементом `("tools.schema", {...})` с проверкой `count == 1` (в `_config()` один инструмент), `approx_tokens > 0`, `names == ["get_server_time"]`;
   - остальные утверждения оставить как есть.

5. Frontend, `frontend/src/pages/AgentEditorPage.tsx`: сразу после `MultiSelect` инструментов (label `t("agentEditor.tools")`) добавить
   ```tsx
   {form.kind === "preset" && form.tools.length >= 10 ? (
     <Alert color="yellow" mt="xs">
       {t("agentEditor.toolsManyHint", { count: form.tools.length })}
     </Alert>
   ) : null}
   ```
   `Alert` уже импортируется в файле. MCP-инструменты входят в `form.tools`, поэтому учитываются автоматически.
   i18n `ru.ts`/`en.ts`, секция `agentEditor`: ключ `toolsManyHint`, ru: `"{{count}} инструментов — JSON-схемы всех уходят в каждый запрос модели. Проверьте, нет ли лишних."`, en: `"{{count}} tools — every JSON schema is sent with each model request. Check for extras."`

---

## Этап 4. Postgres-чекпоинтер (opt-in)

Цель: опционально сохранять состояние графа для реплея и восстановления. Источник истины остаётся `runs`/`run_events`; фича по умолчанию выключена.

1. `backend/pyproject.toml`, `[project].dependencies`: добавить
   ```toml
   "langgraph-checkpoint-postgres>=3,<4",
   "psycopg[binary,pool]>=3.2,<4",
   ```
   затем `cd backend && uv lock` (lock фиксирует точные версии).

2. `backend/app/settings.py`: рядом с retention-настройками добавить
   ```python
   langgraph_checkpoint_enabled: bool = Field(
       default=False, alias="LANGGRAPH_CHECKPOINT_ENABLED"
   )
   langgraph_checkpoint_url: str = Field(default="", alias="LANGGRAPH_CHECKPOINT_URL")
   ```

3. Новый модуль `backend/app/runtime/checkpoint.py`:
   - `_saver: Any | None = None`;
   - `def get_saver() -> Any | None` / `def set_saver(saver: Any | None) -> None`;
   - `def checkpoint_dsn(settings: Settings) -> str` — `settings.langgraph_checkpoint_url or settings.database_url`, с заменой префикса `postgresql+asyncpg://` → `postgresql://` (psycopg не понимает `+asyncpg`);
   - `async def start_checkpointer(settings: Settings, stack: AsyncExitStack) -> None`:
     - сразу `return`, если `not settings.langgraph_checkpoint_enabled`;
     - `saver = await stack.enter_async_context(AsyncPostgresSaver.from_conn_string(checkpoint_dsn(settings)))`;
     - `await saver.setup()` (создаёт таблицы `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`);
     - `set_saver(saver)`;
     - `except Exception as exc: logger.warning("checkpointer disabled: {}", exc); set_saver(None)` — fail-open, запуск приложения не блокируется;
     - импорт: `from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver`.

4. `backend/app/main.py`, `create_app()`: в `lifespan` создать `stack = AsyncExitStack()`; вызвать `await start_checkpointer(settings, stack)` после `refresh_llm_config`; в `finally` (до/после `mcp_server.session_manager.run()` — внутри существующего `finally`) добавить `await stack.aclose()`.

5. `backend/app/agents/execution.py`:
   - сигнатура: `async def stream_agent(agent: AgentConfig, prompt: str, run_override: LLMConfig | None, max_steps: int, *, run_id: str | None = None)`;
   - после формирования `config`: `saver = get_saver()`; если `saver is not None and run_id`: `config["configurable"] = {"thread_id": run_id}`;
   - в вызов `create_react_agent(...)` добавить `checkpointer=saver if run_id else None`.
   Без `run_id` (unit-тесты) поведение не меняется.

6. `backend/app/runtime/manager.py`, вызов `stream_agent` (единственный, ~строка 815): добавить `run_id=run_id`.

7. `backend/app/runtime/retention.py`, `prune_run_events()`: в блок обработки каждого run после удаления `RunEventRow` добавить очистку чекпоинтов, если `settings.langgraph_checkpoint_enabled` и `session.bind is not None and session.bind.dialect.name == "postgresql"`:
   ```python
   for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
       await session.execute(text(f"DELETE FROM {table} WHERE thread_id = :tid"), {"tid": run_id})
   ```
   (порядок важен: сначала `checkpoint_writes`, затем `checkpoint_blobs`, затем `checkpoints`). Уже заархивированные ранее события не пересканируются — при включении фичи «с нуля» устаревших чекпоинтов нет.

8. Конфиг/доки:
   - `docker/.env.example` и `docker/.env.lab.example`: закомментированные строки `# LANGGRAPH_CHECKPOINT_ENABLED=false` и `# LANGGRAPH_CHECKPOINT_URL=`;
   - `infra/k8s/ENV_LAYERS.md`: ключи в разделе ConfigMap;
   - `docs/NUANCES.md`, раздел «Деплой: отклонения от канона»: таблицы чекпоинтера создаёт библиотека (`setup()`), Alembic их не ведёт; фича off по умолчанию; источник истины — `runs`/`run_events`.
   В `infra/k8s/backend.yaml` ключ не добавлять (дефолт `false`).

9. Тесты:
   - `backend/tests/test_retention.py`: с `LANGGRAPH_CHECKPOINT_ENABLED=true` на SQLite `prune_run_events` выполняется без ошибок (SQL-ветка не активируется);
   - `backend/tests/test_execution.py`: `stream_agent(..., run_id="r1")` без saver не добавляет `configurable` — проверка через мок `create_react_agent`, если это не ломает существующий тест.

---

## Critical files & anchors

- `backend/app/agents/execution.py` — `resolve_llm`/`build_llm` (этап 2), `stream_agent` (этапы 3–4), `_agent_tools`/`compose_prompt` (этап 1).
- `backend/app/runtime/manager.py` (~815) — единственный вызов `stream_agent`.
- `backend/app/runtime/retention.py` — `prune_run_events`, очистка чекпоинтов.
- `backend/app/repos/project_settings.py` + `backend/app/main.py` — резолв провайдера и lifespan.
- `frontend/src/pages/SettingsPage.tsx` (`ProviderCard`) и `AgentEditorPage.tsx` (блок инструментов) — UI этапов 2–3.

## Verification

Предусловия: `cd backend`, зависимости через `uv`; для этапов 2–4 — запущенный стек (`docker compose --env-file docker/.env --env-file docker/.env.secrets up -d --build` после правок) и локальный LLM endpoint.

**Этап 1**
```bash
cd backend
uv sync --extra dev --extra studio
uv run langgraph dev --no-browser --port 2024
```
Ожидаемо: в Studio виден граф `dev_agent`; сообщение «Сколько времени?» даёт стрим токенов, вызов `get_server_time`, историю чекпоинтов ≥ 2. Неверный инструмент в снимке → ошибка загрузки графа с путём к файлу.

**Этап 2**
```bash
cd backend && uv run pytest -q tests/test_llm_providers.py tests/test_llm_auth.py
cd ../frontend && npx tsc --noEmit && npm run build
```
E2E: `PATCH /v1/settings/llm/providers/{id}` с `{"extra_body":{"chat_template_kwargs":{"enable_thinking":false}}}` → 200, поле возвращается; `POST /v1/runs` завершается `succeeded`; ответ на `extra_body > 4096` символов — 422.

**Этап 3**
```bash
cd backend && uv run pytest -q tests/test_execution.py
curl -N "$BASE/v1/runs/<run_id>/events" -H "Authorization: Bearer $KEY" | grep tools.schema
```
Ожидаемо: первое событие `tools.schema` с `count`, равным числу собранных инструментов, и `approx_tokens > 0`. В UI редактора агента при 10+ выбранных инструментах появляется жёлтое предупреждение.

**Этап 4**
```bash
cd backend && uv run pytest -q tests/test_retention.py
# локально: LANGGRAPH_CHECKPOINT_ENABLED=true в docker/.env, затем
docker compose --env-file docker/.env --env-file docker/.env.secrets up -d --force-recreate
# прогнать run, затем
docker exec -i ai-agents-backend python - <<'PY'
import asyncio, os, asyncpg
async def main():
    c = await asyncpg.connect(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
    print(await c.fetchval("select count(*) from checkpoints"))
    await c.close()
asyncio.run(main())
PY
```
Ожидаемо: до запуска — 0 (или таблицы отсутствуют при выключенном флаге), после run — ≥ 1; запуск завершается штатно; при `LANGGRAPH_CHECKPOINT_ENABLED=false` таблицы не пополняются.

**Общий регресс**: `cd backend && uv run pytest -q`; `cd frontend && npx tsc --noEmit && npm run build`.

## Assumptions & contingencies

- `langgraph-cli[inmem]` ставится отдельным extra `studio`; CI (`uv sync --extra dev`) остаётся без него.
- `langgraph dev` с `"dependencies": ["."]` импортирует `app` из `backend/.venv`. Если импорт не удаётся — запускать `PYTHONPATH=$PWD uv run langgraph dev` (структура файлов не меняется).
- `ChatOpenAI` (openai 2.54) принимает `extra_body` как dict и передаёт его в тело запроса; если конкретная версия SDK начнёт отклонять параметр — передавать через `model_kwargs={"extra_body": ...}` в `build_llm` (одна правка).
- `AsyncPostgresSaver.setup()` требует DDL-прав у пользователя БД. Если в целевом контуре их нет — фича остаётся выключенной, таблицы создаёт ops вручную тем же `setup()`; код приложения не меняется (fail-open уже предусмотрен).
- Чекпоинтер по умолчанию выключен во всех контурах; включать точечно (`docker/.env`, k8s ConfigMap) после проверки роста таблиц.
- Роутер/супервизор (structured output + специалисты) в этот план не входят: у нас инструменты уже сужаются на агента, а мультиагентная оркестрация — отдельное продуктовое решение.
