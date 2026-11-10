import type { MessageTree } from "./types";

/** Russian UI strings. Key tree must match en.ts. */
const ru: MessageTree = {
  common: {
    refresh: "Обновить",
    add: "Добавить",
    create: "Создать",
    save: "Сохранить",
    cancel: "Отмена",
    delete: "Удалить",
    edit: "Изменить",
    open: "Открыть",
    test: "Проверить",
    copy: "Копировать",
    loading: "Загрузка…",
    error: "Ошибка",
    notice: "Готово",
    search: "Поиск",
    close: "Закрыть",
    back: "Назад",
    yes: "Да",
    no: "Нет",
    all: "Все",
    selectAll: "Выбрать все",
    clearAll: "Снять все",
    none: "Нет",
    enabled: "Включено",
    disabled: "Выключено",
    actions: "Действия",
    name: "Название",
    description: "Описание",
    slug: "Slug",
    status: "Статус",
    updated: "Обновлён",
    created: "Создан",
    theme: "Тема",
    language: "Язык",
    logout: "Выйти",
    settings: "Настройки",
    about: "О сервисе",
    docs: "Документация",
    private: "личный",
    shared: "общий",
    draft: "черновик",
    published: "опубликован",
    archived: "архив",
    personal: "Личный",
    commonVisibility: "Общий",
    emptyDash: "—",
    hide: "Скрыть",
    reset: "Сбросить",
    generate: "Сгенерировать",
    backToList: "К списку",
    loadError: "Ошибка загрузки",
    pageSearchPlaceholder: "Поиск на странице…",
    emptyPageFilter: "Ничего не найдено по поиску.",
    saveFailed: "Не удалось сохранить",
    deleteFailed: "Не удалось удалить",
    viewOnly: "Только просмотр",
    slugImmutable: "Slug неизменяем",
    slugHint: "Латиница, цифры, дефис",
    noDescription: "Без описания",
    emptyParen: "(пусто)",
    authRequired: "Требуется вход",
    unsavedLeave: {
      title: "Несохранённые изменения",
      body: "Есть несохранённые изменения. Сохранить их перед выходом?",
      confirm: "Сохранить",
      discard: "Не сохранять",
    },
  },

  theme: {
    light: "Светлая",
    dark: "Тёмная",
    portracker: "Portracker",
    ariaLabel: "Тема оформления",
  },

  language: {
    en: "English",
    ru: "Русский",
    label: "Язык",
    hint: "Язык интерфейса для подписей и сообщений",
  },

  roles: {
    superadmin: "Суперадминистратор",
    admin: "Администратор",
    user: "Пользователь",
  },

  nav: {
    groups: {
      work: "Создание",
      integrations: "Интеграции",
      analytics: "Аналитика и диагностика",
      administration: "Администрирование",
      help: "Справка",
    },
    items: {
      agents: "Агенты",
      runs: "Запуски агентов",
      schedules: "Расписания",
      tools: "Инструменты",
      skills: "Навыки",
      mcp: "MCP",
      overview: "Обзор",
      users: "Пользователи и роли",
      doctor: "Диагностика",
      notifications: "Уведомления",
      llmProviders: "Провайдеры LLM",
      serviceKeys: "Ключи сервиса",
      packs: "Плагин-пакеты (beta)",
      settings: "Настройки",
      docs: "Документация",
      about: "О сервисе",
    },
    badges: {
      drafts: "черновиков",
      failedRuns: "неудачных запусков",
      disabledMcp: "выключенных подключений",
    },
  },

  userMenu: {
    theme: "Тема",
    language: "Язык",
    settings: "Настройки",
    about: "О сервисе",
    docs: "Документация",
    logout: "Выйти",
  },

  viewToggle: {
    cards: "Плашки",
    table: "Таблица",
  },

  login: {
    title: "ai-agents",
    subtitle: "Панель управления агентами",
    loginFailed: "Не удалось войти",
    loginKeycloak: "Войти через Keycloak",
    cookieHint:
      "Используется cookie-сессия. Для доступа нужна учётная запись в Keycloak.",
  },

  about: {
    title: "О сервисе",
    subtitle: "Control plane агентов ai-agents",
    version: "Версия {{version}}",
    blurb: [
      "ai-agents — control plane ai-agents для сборки, публикации и запуска LLM-агентов. Backend — FastAPI с оркестрацией LangGraph; SPA администрирует агентов, навыки, HTTP/MCP-инструменты и сервисные ключи.",
      "Люди входят через Keycloak (Keycloak OIDC, BFF cookie). Машины — через Bearer сервисные ключи или MCP-ключи с allowlist. Запуски стримят события по SSE.",
      "Инференс LLM идёт на внешний OpenAI-совместимый endpoint (в lab — LM Studio). App-поды GPU не запрашивают.",
    ],
    stackTitle: "Стек",
    stack: [
      "FastAPI + LangGraph + langchain-openai",
      "PostgreSQL (миграции Alembic)",
      "React + TypeScript + Mantine",
      "Keycloak OIDC (Keycloak) + сервисные API-ключи",
      "Traefik / Argo CD / Kustomize / SOPS",
    ],
    linksTitle: "Ссылки",
    links: {
      docs: "Документация в UI",
      api: "OpenAPI / Swagger",
      agentsGuide: "Агенты, навыки и инструменты",
      externalApi: "Внешний API и MCP",
    },
  },

  docs: {
    title: "Документация",
    subtitle: "Практические руководства control plane",
    cards: {
      agentsSkillsTools: {
        title: "Агенты, навыки и инструменты",
        summary:
          "Порядок сборки: инструменты → навыки → агент → тест → публикация. Builtin и HTTP, импорт skills.sh, stale-бейджи.",
        bodyMd: `# Агенты, навыки и инструменты

Практическая инструкция для UI и API. Контракт полей — OpenAPI / \`docs/API.md\`.

Роли: создавать и публиковать могут \`admin\` и \`superadmin\`. Роль \`user\` только смотрит и тестирует **опубликованные общие** агенты.

Рекомендуемый порядок:

\`\`\`text
1. Инструменты (что агент умеет вызывать)
2. Навыки (как действовать — SKILL.md)
3. Агент (промпт + привязка tools/skills) → тест → публикация
\`\`\`

## 1. Инструменты

Инструмент — действие, которое модель может вызвать во время запуска (калькулятор, HTTP API, tool внешнего MCP).

Раздел UI: **«Инструменты»** (\`/tools\`).

### Встроенные

Всегда доступны (привязка по имени): \`calculator\`, \`now\`, \`get_server_time\`. Создавать не нужно — отметьте в редакторе агента.

### Свой HTTP-инструмент

UI: **Инструменты** → «Создать» (или AI-панель → режим form). Заполните slug, name/description, method + URL, parameters, query/headers/body, timeout 1…60 с.

Правила:

- Плейсхолдеры только в path/query, не в host.
- Только \`http(s)\`; private/loopback/metadata запрещены (SSRF-guard).
- Секреты — в \`headers\`; наружу отдаются только \`header_names\`.
- После сохранения нажмите **«Проверить»** с тестовыми \`params\`.

Имя в \`agents.tools\` = **slug**. Правка custom-инструмента действует на **следующие запуски сразу**, без перепубликации. Выключенный/удалённый нельзя привязать или переопубликовать (\`422\`); при удалении отвязывается от всех агентов.

### Инструменты внешнего MCP

1. UI → **MCP** → **«Подключения»** → создать (\`url\`, опционально \`Authorization\`).
2. **«Проверить»** — подтянется список tools.
3. В агенте указать \`mcp:<connection-slug>:<tool-name>\` (пример: \`mcp:internal-docs:search\`).

stdio-MCP не поддерживается (только Streamable HTTP).

## 2. Навыки (skills)

Навык — текст \`SKILL.md\`, который при запуске **добавляется к system prompt**. Это не код и не HTTP-вызов.

Раздел UI: **«Навыки»** (\`/skills\`).

- Вручную: name/description/content; slug можно из названия. Источник \`manual\` правится через UI/\`PATCH\`.
- Импорт с \`https://skills.sh/<owner>/<repo>/<skill>\` (повтор обновляет тот же \`source_id\`).
- С компьютера: файл \`.md\` / \`SKILL.md\` или папка — браузер читает и шлёт \`entries\` (не путь Windows на сервер).

При **публикации** тела скиллов пишутся в snapshot. На запуске тела берутся **live из БД**; правка навыка сразу на следующий run, в UI может появиться stale-бейдж до перепубликации.

## 3. Агенты

Агент = system prompt + tools/skills + (опционально) LLM/лимиты. Запуск требует **опубликованного** агента: prompt/LLM/limits — из snapshot; тела skills/tools — live.

1. Имя, slug (\`^[a-z0-9][a-z0-9-]{1,62}$\`, после создания не меняется).
2. System prompt (обязателен для \`kind=preset\`).
3. Инструменты (builtin / custom / \`mcp:…\`) и навыки.
4. При необходимости модель/temperature (пусто = активный провайдер), \`max_steps\`, \`timeout_seconds\`.
5. Сохранить → **draft** → тест → **Опубликовать**.
   - \`private\` — только владелец (и суперадмин);
   - \`shared\` — виден сервисам и роли \`user\`; во внешнем **MCP** (\`/mcp\`) — только если slug в allowlist ключа.

| Изменение | Нужен publish? |
|---|---|
| system prompt, LLM/limits, kind | **да** |
| список skills/tools у агента | желателен (snapshot); резолв тел — live |
| тело skill / URL/headers custom-tool | **нет** — следующий run; stale-бейджи |

Архив: \`DELETE\` — запуск запрещён, из списков скрыт. Удалить навсегда — только из архива.

## Перед отдачей наружу

1. Тестовый run в UI или \`POST /v1/runs\` + SSE.
2. Убедиться, что tools вызываются (\`tool.call\` / \`tool.result\`).
3. Опубликовать \`shared\`, если нужен внешним системам.
4. Для MCP: slug в allowlist ключа; проверить \`tools/list\` у клиента.

См. также: гайд по внешнему API.`,
      },
      externalApi: {
        title: "Внешний API и MCP",
        summary:
          "Подключение приложений через REST Bearer или MCP Streamable HTTP. URL lab/prod, SSE, allowlist.",
        bodyMd: `# Как подключить внешнее приложение к ai-agents

Полный контракт — OpenAPI / \`docs/API.md\`.

| Способ | Когда выбирать |
|---|---|
| **REST \`/v1/*\`** + Bearer | своё приложение, batch, стрим событий, CRUD агентов |
| **MCP \`/mcp\`** | Cursor, Claude Desktop/Code, тонкие MCP-клиенты |

Базовые URL:

| Контур | URL |
|---|---|
| Lab/work | \`https://ai-agents-dev.example.com\` |
| Prod | \`https://ai-agents.example.com\` |
| Local API | \`http://localhost:8096\` |

## 1. REST (сервисный ключ)

1. Войти под **суперадмином**.
2. **«Ключи сервиса»** → создать со скоупами (\`runs:read/write\`, \`agents:read/write\`, \`admin\`…).
3. Ключ показывается **один раз** — сохранить в секреты приложения.

\`\`\`http
Authorization: Bearer <SERVICE_API_KEY>
Content-Type: application/json
\`\`\`

Минимальный сценарий:

1. \`GET /v1/agents?scope=shared\`
2. \`POST /v1/runs\` с \`{ agent_id, input, metadata }\` → \`run_id\`
3. Стрим \`GET /v1/runs/{id}/events\` или поллинг \`GET /v1/runs/{id}\`
4. Отмена: \`POST /v1/runs/{id}/cancel\`

SSE: \`run.started\`, \`message.delta\`, \`tool.call\` / \`tool.result\`, \`run.completed\` / \`run.failed\` / \`run.cancelled\`. Докачка: \`after=<seq>\`.

Ограничения:

- Только **опубликованный** агент (иначе \`409\`).
- Сервисный ключ видит чужих только если \`shared\` + \`published\`.
- \`agent_id\` — slug или UUID; чужой/невидимый run → \`404\` (не \`403\`).

OpenAPI: \`{BASE}/docs\` → Authorize → \`ServiceBearer\`.

## 2. Общий MCP (IDE и «тонкие» клиенты)

ai-agents — MCP-сервер (Streamable HTTP). Один endpoint; клиенты — разные Bearer-ключи с **allowlist** агентов (\`agent_slugs\`). В список — только \`published\` + \`shared\` из allowlist. Пустой allowlist → нет tools.

1. UI → **MCP** → **«Серверы»** (суперадмин) → создать + allowlist → скопировать \`mcp-ag-…\` один раз.
2. Endpoint: \`{PUBLIC_URL}/mcp\`.

Фрагмент конфига:

\`\`\`json
{
  "mcpServers": {
    "ai-agents": {
      "url": "https://ai-agents-dev.example.com/mcp",
      "headers": { "Authorization": "Bearer mcp-ag-…" }
    }
  }
}
\`\`\`

Tools: \`name\` = slug агента, аргумент \`prompt\` (строка). Вызов = внутренний \`POST /v1/runs\`; клиент получает финальный текст.

Владелец: создать агента → опубликовать \`shared\` → добавить slug в allowlist MCP-ключа.

## 3. Что не путать

| Направление | Суть |
|---|---|
| **MCP наружу** (\`/mcp\`, \`mcp-ag-…\`) | внешние клиенты вызывают **наших** агентов |
| **MCP внутрь** (\`/v1/mcp-connections\`) | **наши** агенты вызывают чужие MCP-tools |

## Чеклист интеграции

- [ ] Выбран контур и \`BASE\`
- [ ] Сервисный или MCP-ключ в секретах
- [ ] Агенты \`shared\` и в allowlist при MCP
- [ ] Smoke: REST run + SSE **или** MCP \`tools/list\` / вызов tool
- [ ] В REST \`metadata\` указан источник
- [ ] Дневной лимит — только для людей с ролью \`user\``,
      },
      apiContract: {
        title: "Обзор API",
        summary:
          "Краткая карта /v1 runs, agents, tools, skills, MCP, assist и моделей авторизации.",
        bodyMd: `# Обзор API

Канонические схемы полей — в OpenAPI (\`{BASE}/docs\`) и \`docs/API.md\`. Здесь — карта для пользователей UI.

## Авторизация

| Principal | Как |
|---|---|
| Человек (SPA) | Keycloak OIDC → BFF cookie; CSRF \`X-Requested-With: ai-agents-ui\` |
| Машина | \`Authorization: Bearer\` сервисный ключ (\`SERVICE_API_KEYS\` или ключ БД + scopes) |
| MCP-клиент | Bearer \`mcp-ag-…\` на \`POST /mcp\` |

## Основные ресурсы

| Область | Prefix | Заметки |
|---|---|---|
| Агенты | \`/v1/agents\` | scopes \`shared\` / \`owned\` / \`archived\` / \`all\`; publish, clone, rollback |
| Запуски | \`/v1/runs\` | create, get, cancel; SSE \`/events\` |
| Инструменты | \`/v1/tools\` | builtin + custom HTTP; test |
| Навыки | \`/v1/skills\` | CRUD manual; import URL / local |
| MCP-подключения | \`/v1/mcp-connections\` | входящие tools для агентов |
| MCP-серверы | \`/api/admin/mcp-servers\` | ключи наружу + allowlist (суперадмин) |
| Сервисные ключи | \`/api/admin/service-keys\` | create / revoke |
| LLM-провайдеры | admin LLM | активный OpenAI-совместимый endpoint |
| Assist | \`/v1/assist/*\` | заполнение форм / советы через активный LLM |
| Статистика | \`/v1/stats/overview\` | агрегаты runs/tools/API |

## Жизненный цикл запуска

\`queued\` → \`running\` → \`succeeded\` | \`failed\` | \`cancelled\`.

Тело создания: \`{ "agent_id": "<slug|uuid>", "input": "...", "metadata": {} }\`.

Для UI предпочтителен SSE; для простых задач — поллинг. Терминальные статусы завершают поток.

## Видимость и publish

- Draft/archived нельзя запускать снаружи (\`409\`).
- \`private\` vs \`shared\` задаёт видимость сверх владельца.
- Внешний MCP и сервисные ключи видят только \`published\` + \`shared\` (плюс allowlist MCP).

## Типичные ошибки

| Код | Смысл |
|---|---|
| \`401\` / \`403\` | нет/запрещена авторизация или роль |
| \`404\` | ресурс невидим или отсутствует (часто чужой run) |
| \`409\` | агент не опубликован / конфликт |
| \`422\` | валидация (мёртвый slug tool, битый \`mcp:…\`) |

Примеры запросов — в гайде по внешнему API и OpenAPI.`,
      },
    },
  },

  settingsPrefs: {
    title: "Настройки",
    languageSection: "Язык",
    languageDescription: "Выберите язык интерфейса. Изменения применяются сразу.",
    themeSection: "Тема",
    themeDescription: "Светлая, тёмная или Portracker для SPA.",
  },

  errorBoundary: {
    title: "Ошибка интерфейса",
    home: "На главную",
  },

  ai-agentsId: {
    label: "Пользователь Keycloak",
    description: "Поиск по логину, имени или email; список догружается при прокрутке",
    placeholder: "Выберите пользователя",
    searchPlaceholder: "Поиск в Keycloak…",
    disabledInDirectory: "отключён в Keycloak",
    loading: "Загружаем…",
    noneFound: "Никого не нашли",
    scrollMore: "Прокрутите, чтобы догрузить ещё",
    endOfList: "Конец списка",
    selected: "Выбран: {{sub}}",
    catalogUnavailable: "Каталог Keycloak недоступен",
  },

  commandPalette: {
    placeholder: "Агент, инструмент, запуск или раздел…",
    empty: "Ничего не найдено",
    loading: "Загружаю…",
    groups: {
      sections: "Разделы",
      agents: "Агенты",
      tools: "Инструменты",
      recentRuns: "Последние запуски",
    },
    toolHintCustom: "свой HTTP-инструмент",
    toolHintBuiltin: "встроенный",
    footer: "↑ ↓ — выбор, Enter — открыть",
  },

  assist: {
    title: "ИИ-ассистент",
    ariaLabel: "ИИ-ассистент",
    modelHint:
      "Модель — активный LLM-провайдер (как у тестовых запусков). Раздел: {{target}}",
    modes: {
      form: { label: "Заполнить", hint: "Сгенерировать значения полей текущей формы" },
      advice: { label: "Подсказать", hint: "Как сделать шаг в сервисе" },
      review: { label: "Проверить", hint: "Разобрать текущую конфигурацию" },
      test: { label: "Тест", hint: "Как проверить: промпт, ожидаемые события" },
    },
    formRequired:
      " — откройте страницу с формой (агент, инструмент, навык, MCP, LLM)",
    emptyHint:
      "Опишите словами, что нужно: «агент для прогноза погоды по Example с инструментом HTTP», «почему агент падает на 4 шаге», «как выдать MCP-ключ для Cursor».",
    you: "Вы",
    assistant: "Ассистент",
    fieldsCount: "полей: {{count}}",
    applyToForm: "Применить к форме",
    thinking: "Думаю…",
    placeholderForm: "Опишите, что заполнить в форме…",
    placeholderAsk: "Задайте вопрос по сервису…",
    enterHint: "Enter — отправить, Shift+Enter — перенос",
    ask: "Спросить",
    clearHistory: "Очистить историю чата",
    appliedNotice: "Поля формы заполнены — проверьте и сохраните",
    pageSearchApplied: "Поиск на странице обновлён",
    pageSearchAndFieldsApplied: "Поиск и поля обновлены — проверьте и сохраните",
    unexpectedFields:
      "Модель вернула поля, которые здесь не применяются — обновлён только поиск.",
    targets: {
      agent: "агент",
      tool: "инструмент",
      llm: "LLM-провайдер",
      "mcp-connection": "MCP-подключение",
      "mcp-server": "MCP-сервер",
      skill: "навык",
      user: "пользователь",
      "service-keys": "сервисные API-ключи",
      general: "общий вопрос",
    },
  },

  agents: {
    title: "Агенты",
    add: "Добавить",
    scopes: {
      all: "Все",
      shared: "Общие",
      owned: "Мои",
      archived: "Архив",
    },
    staleFilter: {
      all: "Все",
      stale: "Устарели",
    },
    emptyFilter: "Ничего не найдено по поиску.",
    visibility: {
      private: "личный",
      shared: "общий",
    },
    staleSkills: "навыки",
    staleSkillsTitle: "Навыки обновились после публикации",
    staleTools: "инструменты",
    staleToolsTitle: "Инструменты обновились после публикации",
    empty: "Агентов нет. Нажмите «Добавить», чтобы создать первого.",
    emptyArchive:
      "Архив пуст. Сюда попадают агенты после «В архив»; из карточки можно удалить навсегда.",
    emptyStale:
      "Нет агентов с устаревшими навыками или инструментами относительно опубликованного снимка.",
    noTools: "без инструментов",
    assistNeedWrite: "Создание агентов доступно роли admin и выше",
    assistDraftFailed: "Не удалось сохранить черновик ассистента — откройте редактор агента и повторите",
    columns: {
      name: "Название",
      tools: "Инструменты",
      visibility: "Видимость",
      status: "Статус",
      updated: "Обновлён",
    },
    runs: "Запуски",
  },

  schedules: {
    title: "Расписания",
    add: "Добавить расписание",
    empty: "Расписаний пока нет.",
    newTitle: "Новое расписание",
    editTitle: "Изменить расписание",
    name: "Название",
    agent: "Агент",
    cron: "Cron",
    cronHint: "5 полей: минута час день месяц день недели",
    timezone: "Часовой пояс",
    input: "Вход",
    enabled: "Включено",
    disabled: "Выключено",
    enable: "Включить",
    disable: "Выключить",
    runNow: "Запустить сейчас",
    deleteConfirm: "Удалить расписание «{{name}}»?",
    columns: {
      name: "Название",
      agent: "Агент",
      cron: "Cron",
      timezone: "Часовой пояс",
      next: "Следующий запуск",
      last: "Последний запуск",
      actions: "Действия",
    },
  },

  runs: {
    title: "Запуски",
    filters: {
      status: "Статус",
      statusAny: "любой",
      agent: "Агент (id или slug)",
      agentPlaceholder: "идентификатор агента",
    },
    columns: {
      run: "Запуск",
      agent: "Агент",
      version: "Версия",
      status: "Статус",
      created: "Создан",
      finished: "Завершён",
    },
    empty: "Запусков нет.",
    compare: "Сравнить",
    selectRun: "Выбрать запуск для сравнения",
    statuses: {
      queued: "queued",
      running: "running",
      waiting_approval: "ожидает подтверждения",
      succeeded: "succeeded",
      failed: "failed",
      cancelled: "cancelled",
    },
  },

  runCompare: {
    title: "Сравнение запусков",
    left: "Левый запуск",
    right: "Правый запуск",
    submit: "Сравнить",
    pickTwo: "Выберите два запуска для сравнения.",
    diffTitle: "Различия harness",
    field: "Поле",
    leftColumn: "Слева",
    rightColumn: "Справа",
    askAssistant: "Спросить ассистента",
    openAgent: "Открыть агента",
    openRun: "Открыть запуск",
    back: "К запускам",
    noDiff: "различий нет",
    differentAgents: "Внимание: запуски разных агентов.",
    assistPrompt:
      "Сравни два запуска агента {{agent}}.\nЛевый {{left}}: {{leftDigest}}\nПравый {{right}}: {{rightDigest}}\nРазличия:\n{{diff}}\n{{differentAgents}}\nПредложи, что изменить в system_prompt, tools и skills, чтобы поведение стало стабильнее. Верни только поля формы агента.",
  },

  runDetail: {
    title: "Запуск",
    breadcrumb: "Запуски",
    notFound: "Запуск не найден",
    noData: "Нет данных",
    backToList: "К списку запусков",
    backShort: "К списку",
    repeat: "Повторить",
    repeatTitle: "Запустить тот же вход тем же агентом",
    cancel: "Отменить",
    params: "Параметры",
    agent: "Агент:",
    version: "Версия:",
    created: "Создан:",
    started: "Начат:",
    finished: "Завершён:",
    input: "Вход",
    metadata: "Metadata",
    result: "Результат",
    emptyOutput: "Пустой ответ",
    events: "События",
    eventsReceived: "получено: {{count}}",
    eventsEmpty: "Поток пуст.",
    harness: "Harness",
    harnessHash: "Отпечаток",
    harnessModel: "Модель",
    harnessLimits: "Лимиты",
    harnessTools: "Инструменты",
    harnessSkills: "Навыки",
    harnessMcp: "MCP",
    harnessUnavailable: "Снимок недоступен для запусков, созданных до появления функции.",
    showHarness: "JSON",
    harnessTitle: "Снимок harness запуска",
    close: "Закрыть",
    digest: "Сводка траектории",
    digestSteps: "Шаги",
    digestDuration: "Длительность",
    digestEvents: "Событий",
    digestOutputChars: "Символов ответа",
    digestNoTools: "Вызовов инструментов нет.",
    digestToolCalls: "Вызовы инструментов",
    digestTool: "Инструмент",
    digestCalls: "Вызовы",
    digestErrors: "Ошибки",
    digestUnfinished: "Незавершённых вызовов: {{count}}",
    digestUnavailable: "Сводка недоступна.",
    digestTokens: "Токены (prompt / completion / total)",
    attempts: "Попытки",
    failureKind: "Класс ошибки",
    parent: "Родительский запуск:",
    depth: "Глубина",
    children: "Дочерние запуски",
    noChildren: "Дочерних запусков нет.",
    downloadTranscript: "Скачать транскрипт",
    transcriptArchived: "Транскрипт архивирован, доступна сводка.",
    approvalRequired: "Требуется подтверждение изменяющего инструмента",
    approvalTool: "Инструмент",
    approvalInput: "Аргументы",
    approve: "Подтвердить",
    reject: "Отклонить",
    approvalError: "Не удалось принять решение",
  },

  tools: {
    title: "Инструменты",
    add: "Добавить",
    newTitle: "Новый инструмент",
    editTitle: "Инструмент: {{name}}",
    aiTitle: "AI-автозаполнение",
    aiHint:
      "Опишите инструмент словами — LLM заполнит URL, метод, параметры и шаблон тела. Секреты в заголовках остаются пустыми.",
    aiPlaceholder: "Например: прогноз погоды по городу через open-meteo",
    fillFields: "Заполнить поля",
    describeRequired: "Опишите инструмент хотя бы одной фразой",
    noFieldsFromModel: "Модель не предложила ни одного поля, применимого к этой форме",
    nameRequired: "Укажите название инструмента",
    slugRequired: "Укажите slug инструмента",
    urlRequired: "Укажите URL инструмента",
    paramNameRequired: "У каждого параметра должно быть имя",
    saved: "Инструмент «{{name}}» сохранён",
    created: "Инструмент «{{name}}» создан",
    deleted: "«{{name}}» удалён",
    deletedDetached: "«{{name}}» удалён и отвязан от агентов: {{agents}}",
    method: "Метод",
    url: "URL",
    urlHint: "Шаблон: {param} в пути подставляется с URL-кодированием",
    headers: "Headers",
    headersHintCreate: "По строке на заголовок: K: V",
    headersHintEditEmpty: "Пустое поле — не менять; иначе задать заголовки (K: V)",
    headersHintEditSaved:
      "Сохранены: {{names}}. Пустое поле — не менять; иначе заменить целиком (K: V)",
    headersKeepPlaceholder: "оставить пустым = сохранить",
    query: "Query",
    queryHint: "По строке на параметр: K: V",
    bodyTemplate: "body_template",
    bodyTemplateHint: "JSON-шаблон тела запроса (для POST/PUT/PATCH)",
    enabled: "Включён",
    on: "вкл",
    off: "выкл",
    enabledLong: "включён",
    disabledLong: "выключен",
    parameters: "Параметры",
    addParam: "Добавить параметр",
    noParams: "Параметров нет. Добавьте те, которые агент будет передавать в инструмент.",
    paramName: "Имя",
    paramType: "Тип",
    paramRequired: "Обязательный",
    paramEnumHint: "Значения через запятую; пусто — без ограничения",
    schemaTitle: "Схема: {{name}}",
    schemaShort: "Схема",
    schemaParams: "Схема параметров",
    testTitle: "Проверка: {{name}}",
    testTitleFallback: "Проверка инструмента",
    testParams: "Параметры (JSON)",
    testParamsHint: "Объект с параметрами вызова",
    testInvalidJson: "Параметры должны быть корректным JSON",
    testExpectObject: "Ожидается JSON-объект с параметрами",
    emptyResponse: "(пустой ответ)",
    deleteTitle: "Удалить инструмент?",
    deleteBody: "«{{name}}» будет удалён без возможности восстановления.",
    deleteInUse: "Используется в агентах: {{total}}",
    draftAgent: "{{slug}} (черновик)",
    publishedAgent: "{{slug}} (v{{version}})",
    builtinSection: "Встроенные",
    customSection: "Свои инструменты",
    showDetails: "Показать URL",
    hideDetails: "Скрыть URL",
    customEmpty: "Своих инструментов пока нет — создайте HTTP-инструмент без кода.",
    emptyFilter: "Ничего не найдено по поиску.",
    builtinEmpty: "Встроенные инструменты не зарегистрированы.",
    sourceCustom: "свой HTTP",
    sourceBuiltin: "встроенный",
    alwaysAvailable: "всегда доступен",
    paramsShort: "{{count}} пар.",
    deleteChecking: "Проверяем, какие агенты используют инструмент…",
    deleteDetachHint: "Инструмент будет автоматически удалён из состава этих агентов:",
    deleteUnused: "Ни один агент этот инструмент не использует.",
    runTest: "Выполнить",
    urlPlaceholder: "https://api.example.com/items/{id}",
    authPlaceholder: "Authorization: Bearer …",
    columns: {
      name: "Название",
      source: "Источник",
      methodUrl: "Метод и URL",
      parameters: "Параметры",
      status: "Статус",
    },
  },

  skills: {
    title: "Навыки",
    add: "Добавить",
    addTitle: "Добавить навык",
    editTitle: "Навык: {{name}}",
    detailTitle: "Навык",
    intro:
      "Навык — это SKILL.md с процедурными инструкциями. Подключается к агенту в его карточке и попадает в системный промпт при запуске.",
    filterPlaceholder: "Фильтр по имени, slug, описанию",
    empty: "Навыки не импортированы.",
    emptyFilter: "Ничего не найдено по поиску.",
    tabs: {
      manual: "Свой навык",
      import: "skills.sh",
      local: "С компьютера",
    },
    aiTitle: "Сгенерировать с ИИ",
    aiHint:
      "Опишите навык словами — LLM заполнит название, slug, описание и SKILL.md (разделы «Когда использовать», «Инструкции», «Пример», «Чек-лист»).",
    aiPlaceholder:
      "Например: навык проверки пул-реквеста — что смотреть, в каком порядке, какие критерии",
    describeRequired: "Опишите навык хотя бы одной фразой",
    noFieldsFromModel: "Модель не предложила ни одного поля навыка",
    nameRequired: "Укажите название навыка",
    contentRequired: "Добавьте SKILL.md — вручную или сгенерируйте с ИИ",
    slugHint: "Латиница, цифры, дефис; пусто — из названия",
    contentLabel: "SKILL.md",
    contentHint:
      "YAML frontmatter + разделы; сохраняется как навык и попадает в промпт агента",
    saved: "Навык «{{name}}» сохранён",
    created: "Навык «{{name}}» создан",
    deleted: "Навык «{{name}}» удалён",
    imported: "Навык «{{name}}» импортирован",
    importStatsCreated: "создано: {{count}}",
    importStatsUpdated: "обновлено: {{count}}",
    importStatsSkipped: "пропущено: {{count}}",
    importMulti: "Импорт навыков ({{parts}}): {{names}}",
    importSingle: "Навык «{{name}}» импортирован ({{parts}})",
    importUrlTitle: "Импорт с skills.sh",
    importUrlHint:
      "Найдите навык на skills.sh, скопируйте ссылку вида https://skills.sh/<owner>/<repo>/<skill> и вставьте ниже.",
    importUrlLabel: "Ссылка на навык",
    importUrlRequired: "Укажите ссылку на навык skills.sh",
    importButton: "Импортировать",
    importFailed: "Импорт не удался",
    localTitle: "С вашего компьютера",
    localHint:
      "Сначала выберите SKILL.md или папку навыка, проверьте список файлов, затем нажмите «Импортировать». Файлы читаются в браузере — путь на сервер не нужен.",
    pickFile: "Выбрать файл",
    pickFolder: "Выбрать папку",
    readyToImport: "Готово к импорту",
    selectedFiles:
      "Выбрано файлов: {{count}}. Импорт начнётся только после подтверждения.",
    noSkillMd:
      "В выборе нет SKILL.md / .md — укажите файл навыка или папку, где он лежит",
    pickFirst: "Сначала выберите файл или папку",
    deleteTitle: "Удалить навык?",
    deleteBody:
      "«{{name}}» будет удалён. Агенты, где он подключён, потеряют эти инструкции после следующей публикации.",
    installed: "Установленные",
    source: "Источник",
    content: "Содержимое",
    filesCount: "Файлы ({{count}})",
    noExtraFiles: "Дополнительных файлов нет.",
  },

  mcp: {
    title: "MCP",
    addServer: "Сервер",
    addConnection: "Подключение",
    tabs: {
      servers: "Серверы (наружу)",
      connections: "Подключения (внутрь)",
    },
    serversIntro:
      "Агенты со статусом «опубликован» и видимостью «общий» доступны внешним MCP-клиентам (Cursor, Claude Desktop) как инструменты. Один ключ = один клиент.",
    serversEmpty: "MCP-серверов нет.",
    connectionsEmpty: "MCP-подключений нет.",
    connectionsIntro:
      "Входящие подключения открывают агентам tools удалённых MCP как mcp:<slug>:<tool>.",
    newServer: "Новый MCP-сервер",
    editServer: "Изменить MCP-сервер",
    newConnection: "Новое подключение",
    editConnection: "Изменить подключение",
    serverHintCreate:
      "Метка внешнего клиента. После создания остаётесь здесь: скопируйте JSON для клиента (ключ — один раз). Пустые allowlist — клиент ничего не увидит.",
    serverHintEdit:
      "Allowlist для ключа (агенты / tools / skills). Ниже — JSON для клиента; «Новый ключ» ротирует секрет.",
    agentsAllowlist: "Агенты (allowlist)",
    agentsAllowlistHint:
      "Published + shared эксперты (полный run + LLM). Пусто — без агентов.",
    toolsAllowlist: "Инструменты (allowlist)",
    toolsAllowlistHint:
      "Атомарные tools без LLM агента (в MCP: tool__slug). Пусто — без tools.",
    skillsAllowlist: "Навыки (allowlist)",
    skillsAllowlistHint:
      "Доступен get_skill для этих slug. Пусто — get_skill нет.",
    noPublishedShared: "Нет опубликованных общих агентов",
    noTools: "Нет инструментов",
    noSkills: "Нет навыков",
    assistServerHint:
      "Заполни MCP-сервер для Cursor на ноутбуке: короткий slug и понятное имя",
    headersJson: "Заголовки (JSON)",
    headersKeep: "Оставьте пустым, чтобы не менять сохранённые заголовки",
    headersExample: 'Например {"Authorization": "Bearer …"}',
    timeoutSec: "Таймаут, с",
    enabledSwitch: "Включено",
    active: "активен",
    inactive: "выключен",
    enabledShort: "включено",
    disabledShort: "выключено",
    allowlistEmpty: "allowlist пуст",
    noHeaders: "без заголовков",
    notTested: "не проверялось",
    toolsCached: "инструментов: {{count}}",
    newKey: "Новый ключ",
    enable: "Включить",
    disable: "Отключить",
    check: "Проверить",
    keyOnce:
      "Ключ показывается один раз — сохраните его в конфиг клиента сейчас.",
    keyNotShown:
      "Секрет не хранится. Создайте новый ключ, чтобы получить готовый JSON для клиента.",
    keyRotated: "Выдан новый ключ — скопируйте конфиг",
    copyConfig: "Скопировать конфиг",
    clientConfigTitle: "Конфиг клиента (JSON)",
    serverCreated: "MCP-сервер «{{name}}» создан — скопируйте ключ",
    serverUpdated: "MCP-сервер «{{name}}» обновлён",
    serverDeleted: "MCP-сервер «{{name}}» удалён",
    connectionSaved: "Подключение сохранено",
    connectionCreated: "Подключение создано",
    connectionDeleted: "Подключение удалено",
    connectionDeletedDetached:
      "Подключение удалено; отвязано от агентов: {{agents}}",
    headersError: "Заголовки: {{message}}",
    testOk: "Подключение «{{slug}}»: инструментов {{count}}",
    testFail: "Подключение «{{slug}}» недоступно",
    noServerFields: "Модель не предложила ни одного поля MCP-сервера",
    noConnectionFields: "Модель не предложила ни одного поля MCP-подключения",
    assistHintServers:
      "Один ключ = один клиент; agent_slugs = allowlist published+shared",
    assistHintConnections: "Инструменты агентам доступны как mcp:<slug>:<tool>",
    columns: {
      name: "Имя",
      slug: "slug",
      agents: "Агенты",
      status: "Статус",
      used: "Использован",
      url: "URL",
      tools: "Инструменты",
      headers: "Заголовки",
    },
    presets: {
      cursor: {
        label: "Cursor",
        name: "Cursor (рабочее место)",
        description: "Ключ для Cursor IDE на этом рабочем месте",
      },
      claudeDesktop: {
        label: "Claude Desktop",
        name: "Claude Desktop",
        description: "Ключ для Claude Desktop",
      },
      ciBot: {
        label: "CI / бот",
        name: "CI / автоматизация",
        description: "Сервисный MCP-клиент для CI или бота",
      },
    },
    namePlaceholderServer: "Cursor (ноутбук)",
    fillViaAi: "Заполнить через AI",
    authTemplate: "Шаблон Authorization",
    configPreviewTitle: "Пример конфига клиента (плейсхолдер ключа до создания)",
    connectionUrlHint:
      "После сохранения инструменты доступны агентам как mcp:<slug>:<tool>.",
    headersCount: "headers: {{count}}",
    headersList: "headers: {{names}}",
  },

  packs: {
    title: "Плагин-пакеты (beta)",
    refresh: "Обновить",
    add: "Добавить пакет",
    save: "Сохранить пакет",
    manifest: "Манифест JSON",
    importHint:
      "Вставьте JSON-манифест. Агенты только preset; skills/tools должны уже существовать. YAML поддерживается для пакетов в сборке.",
    deleteConfirm: "Удалить пользовательский пакет «{{name}}»? Установленные агенты останутся.",
    empty: "В этой сборке нет зарегистрированных пакетов.",
    notInstalled: "не установлен",
    dryRun: "Пробный прогон",
    install: "Установить",
    dryRunHint: "Только предпросмотр: ничего не записано.",
    installDone: "Пакет установлен.",
    alreadyInstalled: "Эта версия пакета уже установлена.",
    noChanges: "Изменений агентов нет.",
    agents: "Агенты",
    skills: "Навыки",
    tools: "Инструменты",
    entity: "Сущность",
    ref: "Ссылка",
    action: "Действие",
    columns: {
      name: "Пакет",
      description: "Описание",
      refs: "Состав",
      installed: "Установлен",
      actions: "Действия",
    },
    actions: {
      create: "создать",
      update: "обновить",
      noop: "без изменений",
    },
    sources: {
      code: "из сборки",
      custom: "свой",
    },
  },

  notifications: {
    title: "Уведомления",
    add: "Добавить канал",
    refresh: "Обновить",
    empty: "Каналов пока нет.",
    newTitle: "Новый канал",
    editTitle: "Изменить канал",
    name: "Название",
    kind: "Тип",
    url: "Webhook URL",
    chatId: "Telegram chat id",
    secret: "Секрет подписи",
    secretHint: "Для X-Ai-Agents-Signature; после сохранения не показывается",
    enabled: "Включено",
    disabled: "Выключено",
    secretConfigured: "секрет задан",
    deliveries: "Последние доставки",
    noDeliveries: "Доставок пока нет.",
    deleteConfirm: "Удалить канал «{{name}}»?",
    columns: {
      name: "Название",
      kind: "Тип",
      target: "Адрес",
      status: "Статус",
      actions: "Действия",
      run: "Запуск",
      channel: "Канал",
      attempts: "Попытки",
      created: "Создано",
      error: "Ошибка",
    },
    statuses: {
      pending: "ожидает",
      sent: "отправлено",
      failed: "ошибка",
    },
  },

  users: {
    title: "Пользователи и роли",
    add: "Добавить",
    addTitle: "Добавить пользователя",
    intro:
      "Роль user — только просмотр и тест опубликованных общих агентов; лимит запусков в сутки задаётся здесь или в USER_DAILY_RUN_LIMIT. Роль admin — CRUD и публикация своих агентов/скиллов, без управления доступами и настройками. Назначать и снимать superadmin может только bootstrap-аккаунт (SUPERADMIN_EMAILS), остальные суперадмины управляют лишь admin/user.",
    columns: {
      user: "Пользователь",
      role: "Роль",
      changeRole: "Изменить роль",
      dailyLimit: "Лимит / сутки",
      runsToday: "Запусков сегодня",
      login: "Вход",
    },
    roleOptions: {
      superadmin: "Суперадмин — всё",
      admin: "Админ — свои агенты/скиллы",
      user: "Пользователь — просмотр и тест",
    },
    roleSelect: "Роль",
    roleSuperadminHint:
      "Суперадминов назначает только bootstrap-аккаунт (SUPERADMIN_EMAILS)",
    dailyLimit: "Лимит запусков в сутки",
    dailyLimitHint: "Пусто — значение из env",
    dailyLimitPlaceholder: "из env",
    updated: "Пользователь {{id}} обновлён",
    created: "Пользователь {{id}} добавлен",
    noUserFields: "Модель не предложила ни одного поля пользователя",
    superadminOnlyBootstrap:
      "Назначать суперадминов может только bootstrap-аккаунт (SUPERADMIN_EMAILS)",
  },

  doctor: {
    title: "Диагностика платформы",
    refresh: "Обновить",
    ok: "Готово",
    failed: "Есть проблемы",
    check: "Проверка",
    status: "Статус",
    message: "Сообщение",
    details: "Детали",
    showJson: "JSON",
    jsonTitle: "Детали проверки",
    fields: {
      current: "ревизия",
      heads: "ожидается",
      model: "модель",
      models: "моделей",
      oidc: "OIDC",
      service_keys: "ключи сервиса",
      path: "путь",
      writable: "запись",
      free_gb: "свободно ГиБ",
      queued: "в очереди",
      running: "выполняется",
      total: "всего",
      oldest_seconds: "старейший, с",
      approvals_pending: "подтверждений",
      per_agent: "по агентам",
      last_run_seconds_ago: "последний запуск, с",
      limit_seconds: "лимит, с",
      pending: "ожидает",
      failed_24h: "ошибок за 24ч",
      by_failure_kind: "по типу",
      connections: "подключений",
      errors: "ошибки",
    },
    statuses: {
      ok: "ok",
      warn: "warn",
      error: "error",
      skip: "skip",
    },
  },

  serviceKeys: {
    title: "Ключи сервиса",
    forbiddenTitle: "Доступ запрещён",
    forbiddenBody: "Раздел доступен только суперадминистратору.",
    newKey: "Новый ключ",
    scopes: "Права (scopes)",
    scopesHint:
      "Выберите пресет или отметьте scopes вручную. *:write — CRUD каталога; *:execute — действие.",
    scopePresets: {
      label: "Пресет:",
      consume: "Чтение и исполнение",
      consumeHint:
        "Для внешнего приложения / фабрики: каталог, invoke tools и runs. Без CRUD и admin.",
      manage: "Управление каталогом",
      manageHint:
        "Чтение, исполнение и CRUD агентов/tools/skills. Без admin-настроек.",
      full: "Полный доступ",
      fullHint: "Все scopes, включая admin (настройки LLM и машинный admin).",
    },
    createKey: "Создать ключ",
    updateChanges: "Применить изменения",
    nameAndScopeRequired: "Укажите название и хотя бы один scope",
    keyOnce: "Ключ показывается один раз — сохраните его сейчас.",
    empty: "Ключей нет.",
    agentsAllowlist: "Агенты (каталог)",
    toolsAllowlist: "Инструменты (каталог)",
    skillsAllowlist: "Навыки (каталог)",
    allowlistHint:
      "Fail-closed для /v1/catalog и invoke: пустой список запрещает категорию.",
    scopeLabels: {
      agents_read: "Чтение агентов",
      agents_write: "Управление агентами",
      tools_read: "Чтение инструментов",
      tools_execute: "Вызов инструментов",
      tools_write: "Управление инструментами",
      skills_read: "Чтение навыков",
      skills_write: "Управление навыками",
      runs_read: "Чтение запусков",
      runs_execute: "Запуск агентов",
      admin: "Админ-настройки",
    },
    scopeHints: {
      agents_read: "Список/карточки агентов и секция agents в /v1/catalog.",
      agents_write: "CRUD и публикация агентов, MCP-подключения; AI-подсказки для агентов.",
      tools_read: "Спеки инструментов и секция tools в /v1/catalog.",
      tools_execute: "POST /v1/tools/…/invoke без LLM агента. Это не tools:write.",
      tools_write: "CRUD кастомных HTTP-tools. Не даёт право на invoke.",
      skills_read: "Чтение content навыков и секция skills в /v1/catalog.",
      skills_write: "Создание, импорт, правка и удаление навыков (CRUD).",
      runs_read: "Просмотр запусков, SSE-событий и статистики.",
      runs_execute: "Старт и отмена запусков (POST /v1/runs). Старый алиас: runs:write.",
      admin: "Менять LLM-провайдеров и прочие админ-настройки (полный машинный admin).",
    },
    columns: {
      name: "Название",
      scopes: "Права",
      catalog: "Каталог",
      status: "Статус",
      created: "Создан",
      used: "Использован",
    },
    active: "активен",
    revoked: "отозван",
    revoke: "Отозвать",
    restore: "Восстановить",
    delete: "Удалить",
    deleteTitle: "Удалить ключ «{{name}}»?",
    deleteBody: "Ключ будет удалён безвозвратно. «Отозвать» только отключает его; отозванный ключ можно восстановить с тем же значением до удаления.",
    deleted: "Ключ «{{name}}» удалён",
  },

  stats: {
    title: "Обзор",
    since: "с {{date}}",
    windows: {
      d7: "7 дней",
      d14: "14 дней",
      d30: "30 дней",
    },
    cards: {
      runs: "Запуски",
      successRate: "Успешность",
      toolCalls: "Вызовы инструментов",
      tokens: "Токены",
      apiRequests: "API-запросы",
      apiErrors: "Ошибки API",
      apiP95: "p95 API",
    },
    runsDaily: "Запуски по дням",
    forPeriod: "{{count}} за период",
    statusSucceeded: "успешно",
    statusFailed: "ошибки",
    statusCancelled: "отменено",
    apiSeries: "API: запросы и ошибки",
    seriesRequests: "запросы",
    seriesErrors: "ошибки",
    toolsDaily: "Вызовы инструментов по дням",
    seriesCalls: "вызовы",
    topTools: "Топ инструментов",
    noToolCalls: "Вызовов пока не было.",
    agents: "Агенты",
    noAgentRuns: "Запусков пока не было.",
    agentColumns: {
      agent: "Агент",
      runs: "Запуски",
      succeeded: "Успешно",
      failed: "Ошибки",
      tokens: "Токены",
      avgTime: "Ср. время",
    },
    queue: "Очередь: {{count}}",
    oldestQueued: "Старейший: {{value}} с",
    topEndpoints: "API: популярные эндпоинты",
    noApiRequests: "Запросов пока не было.",
    endpointColumns: {
      method: "Метод",
      path: "Путь",
      calls: "Вызовы",
      errors: "Ошибки",
      p95: "p95",
    },
    ms: "{{value}} мс",
    sec: "{{value}} с",
  },

  agentEditor: {
    breadcrumbNew: "Новый агент",
    titleNew: "Новый агент",
    aiTitle: "AI-автозаполнение",
    aiHint:
      "Опишите агента словами — LLM заполнит название, промпт, инструменты и скиллы. Модель и лимиты остаются вашими.",
    aiPlaceholder:
      "Например: агент-помощник по расчётам — считает выражения и подсказывает время по Москве",
    missingTools:
      "Не хватает инструментов: {{list}} — создайте их на вкладке «Инструменты».",
    basics: "Основное",
    systemPrompt: "Системный промпт",
    kind: "Тип агента",
    kindPreset: "Preset — обычный агент",
    kindPlugin: "Plugin — код разработчика",
    kindPresetHint: "Промпт, tools, навыки и память работают во встроенном ReAct-цикле.",
    kindPluginHint: "Без промпта/tools: backend вызывает обработчик, зарегистрированный по имени.",
    pluginName: "Имя плагина",
    pluginHint: "Имя из backend/app/agents/plugins.py; нужна пересборка backend.",
    pluginAlert: "Плагин — это код, а не данные. Добавить его и пересобрать backend может только разработчик; агент лишь ссылается на зарегистрированное имя.",
    tools: "Инструменты",
    toolsHint: "Правки инструмента применяются сразу, без перепубликации",
    toolsNotFound: "Инструменты не найдены",
    skills: "Скиллы",
    skillsHint: "Импортированные скиллы skills.sh",
    skillsNotFound: "Скиллы не найдены",
    subAgents: "Субагенты",
    subAgentsHint: "Только опубликованные агенты, доступные вам (свои или общие), кроме текущего.",
    memoryEnabled: "Память агента",
    memoryHint: "Включает три встроенных tool: memory_write, memory_search, memory_delete. В каталоге инструментов их нет; записи изолированы по агенту и пользователю.",
    memory: "Сохранённая память",
    memoryEmpty: "Записей пока нет.",
    memoryKey: "Ключ",
    memoryContent: "Содержимое",
    memoryTags: "Теги",
    memoryUpdated: "Обновлено",
    toolsGroupBuiltinHttp: "Встроенные и HTTP",
    toolsGroupOther: "Прочее",
    llm: "LLM",
    llmGlobalHint: "Пусто — глобальный LLM-провайдер приложения. Переопределяйте только для отдельной модели/endpoint.",
    llmOverride: "Переопределить LLM для агента",
    temperature: "Температура",
    temperatureHint: "0–1, не проценты: 0 — детерминированно, 1 — креативно.",
    model: "Модель",
    limits: "Лимиты",
    maxTokens: "max_tokens",
    maxAttempts: "max_attempts",
    approvalMode: "Подтверждение вызовов инструментов",
    approvalHint: "Спрашивать человека перед вызовом: mutating — POST/PUT/PATCH/DELETE HTTP и любые MCP-tools; all — любые tools; never — без подтверждения. Ожидание входит в timeout запуска.",
    approvalModes: {
      mutating: "Только изменяющие",
      all: "Все инструменты",
      never: "Без подтверждения",
    },
    clone: "Клонировать",
    archive: "В архив",
    purge: "Удалить навсегда",
    publish: "Опубликовать",
    publishSection: "Публикация",
    visibilityPrivate: "Личный",
    visibilityShared: "Общий",
    publishedVersion: "Опубликованная версия: {{version}}",
    neverPublished: "Ещё не публиковался",
    versions: "Версии",
    noVersions: "Версий пока нет",
    versionCol: "Версия",
    createdCol: "Создана",
    authorCol: "Автор",
    current: "текущая",
    rollback: "Откатить",
    testRun: "Тестовый запуск",
    publishFirst: "Сначала опубликуйте агента",
    input: "Вход",
    defaultTestInput: "Привет! Посчитай 17*4+9.",
    run: "Запустить",
    preflight: "Проверить готовность",
    preflightTitle: "Preflight агента",
    preflightOk: "Готов к запуску",
    preflightFailed: "Не готов",
    preflightCheck: "Проверка",
    preflightStatus: "Статус",
    preflightMessage: "Сообщение",
    preflightEffective: "Действующий конфиг",
    preflightModel: "Модель",
    preflightBaseUrl: "Base URL",
    preflightVersionNote: "Проверяется опубликованная версия v{{version}}.",
    preflightClose: "Закрыть",
    preflightChecks: {
      agent: "Агент",
      plugin: "Плагин",
      quota: "Дневная квота",
      tools: "Инструменты",
      skills: "Навыки",
      mcp: "MCP",
      llm: "LLM",
      limits: "Лимиты",
    },
    eventsCount: "событий: {{count}}",
    runFailed: "Запуск завершился ошибкой",
    nameRequired: "Укажите название агента",
    slugRequired: "Укажите slug агента",
    created: "Агент создан",
    saved: "Изменения сохранены",
    describeRequired: "Опишите агента хотя бы одной фразой",
    filledNotice: "Поля заполнены — проверьте и сохраните",
    saveFirst: "Сначала сохраните агента",
    publishedNotice: "Агент опубликован (visibility={{visibility}})",
    cloned: "Создана копия «{{name}}»",
    rolledBack:
      "Откат на v{{version}}: опубликована новая версия v{{published}}",
    archived: "Агент переведён в архив",
    purgeOnlyArchive: "Удалить навсегда можно только агента из архива",
    noFieldsFromModel: "Модель не предложила ни одного поля, применимого к этой форме",
    staleSnapshotTitle: "Снимок версии устарел",
    staleSnapshotBody:
      "Изменения навыков и custom-инструментов уже действуют в следующих запусках. Перепубликация обновит snapshot{{version}} и снимет бейджи.",
    viewOnlyBody:
      "Роль «Пользователь» может просматривать опубликованных агентов и запускать тестовый запрос, но не изменять их.",
    rollbackTitle: "Откатить на v{{version}}?",
    rollbackBody:
      "Конфигурация (промпт, скиллы, LLM, лимиты) будет взята из снимка v{{version}}. История не переписывается: будет создана и опубликована новая версия, а текущее содержимое черновика заменится.",
    rollbackToolsNote:
      "Инструменты применяются вживую и в снимок не откатываются — останется текущий список инструментов агента.",
    purgeTitle: "Удалить «{{name}}» навсегда?",
    purgeBody:
      "Агент и история версий будут удалены без возможности восстановления. Уже завершённые запуски останутся в журнале.",
    agentFallback: "агента",
  },

  llmSettings: {
    title: "Провайдеры LLM",
    addProvider: "Добавить провайдера",
    newProvider: "Новый провайдер",
    viewOnlyBody: "Управлять провайдерами и активной моделью может суперадминистратор.",
    effectiveEndpoint: "Действующий эндпоинт",
    sourceProvider: "активный провайдер",
    sourceLegacy: "legacy-настройки",
    sourceEnv: "env",
    modelUnset: "модель не задана",
    keySet: " · ключ задан",
    keyMissing: " · без ключа",
    effectiveHint:
      "Применяется к запускам агентов и AI-автозаполнению, если у агента не задан свой base_url/модель.",
    empty:
      "Провайдеров нет — используются переменные окружения (DEFAULT_LLM_*).",
    providerName: "Имя провайдера",
    providerNamePlaceholder: "LM Studio / vLLM / внешний API",
    preset: "Пресет",
    presetHint: "Подставит base_url и схему авторизации; всё можно править",
    presetHintShort: "Подставит base_url и схему авторизации",
    presetNone: "не выбран",
    auth: "Авторизация",
    authHeader: "Заголовок",
    authPrefix: "Префикс ключа",
    authPrefixHint: "Например «Bearer » или пусто",
    authKeyPreview: "Отправляется как {{header}}: {{prefix}}<ключ>",
    apiKey: "API-ключ",
    apiKeyHintLocal: "Можно оставить пустым для локальных серверов",
    apiKeySaved: "Ключ сохранён ({{hint}}); пустое поле — не менять",
    apiKeyUnset: "Ключ не задан",
    model: "Модель",
    modelHint: "Список приходит от провайдера; можно вписать вручную",
    modelHintCreate: "После создания можно выбрать из списка провайдера",
    modelPlaceholder: "Загрузите список моделей",
    fetchModels: "Получить модели",
    makeActive: "Сделать активным",
    activeBadge: "активный",
    updatedAt: "Обновлён: {{date}}",
    modelsFetched: "Моделей от «{{name}}»: {{count}}",
    providerSaved: "Провайдер «{{name}}» сохранён",
    providerActive: "Активный провайдер: «{{name}}»",
    providerDeleted: "Провайдер «{{name}}» удалён",
    providerAdded: "Провайдер добавлен — при необходимости сделайте его активным",
    noProviderFields: "Модель не предложила ни одного поля провайдера",
    deleteTitle: "Удалить провайдера «{{name}}»?",
    deleteBody: "Провайдер будет удалён без возможности восстановления.",
    deleteActiveNote:
      " Он сейчас активный: агенты и автозаполнение вернутся к env/legacy-настройкам.",
    authTypes: {
      bearer: {
        label: "Authorization: Bearer <ключ>",
        short: "Bearer",
        hint: "Стандарт OpenAI-совместимых API",
      },
      custom: {
        label: "Свой заголовок и префикс",
        short: "Свой заголовок",
        hint: "Например x-api-key без префикса",
      },
      none: {
        label: "Без авторизации",
        short: "Без авторизации",
        hint: "Локальные LM Studio / Ollama",
      },
    },
    presets: {
      openaiCompat: {
        label: "OpenAI-совместимый",
        note: "Любой /v1 с OpenAI API (vLLM, шлюзы, облака)",
      },
      lmStudio: {
        label: "LM Studio",
        note: "Локальный сервер на хосте, ключ не нужен",
      },
      ollama: {
        label: "Ollama",
        note: "OpenAI-совместимый /v1 Ollama",
      },
      anthropicGateway: {
        label: "Anthropic-совместимый шлюз",
        note: "Нужен OpenAI-совместимый шлюз: ключ уходит в x-api-key",
      },
    },
  },
} as const;

export default ru;
