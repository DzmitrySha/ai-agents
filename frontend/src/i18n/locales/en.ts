/** English UI strings (source language). Keep key tree in sync with ru.ts. */
const en = {
  common: {
    refresh: "Refresh",
    add: "Add",
    create: "Create",
    save: "Save",
    cancel: "Cancel",
    delete: "Delete",
    edit: "Edit",
    open: "Open",
    test: "Test",
    copy: "Copy",
    loading: "Loading…",
    error: "Error",
    notice: "Done",
    search: "Search",
    close: "Close",
    back: "Back",
    yes: "Yes",
    no: "No",
    all: "All",
    selectAll: "Select all",
    clearAll: "Clear all",
    none: "None",
    enabled: "Enabled",
    disabled: "Disabled",
    actions: "Actions",
    name: "Name",
    description: "Description",
    slug: "Slug",
    status: "Status",
    updated: "Updated",
    created: "Created",
    theme: "Theme",
    language: "Language",
    logout: "Log out",
    settings: "Settings",
    about: "About",
    docs: "Docs",
    private: "private",
    shared: "shared",
    draft: "draft",
    published: "published",
    archived: "archived",
    personal: "Personal",
    commonVisibility: "Shared",
    emptyDash: "—",
    hide: "Hide",
    reset: "Reset",
    generate: "Generate",
    backToList: "Back to list",
    loadError: "Load error",
    pageSearchPlaceholder: "Search on this page…",
    emptyPageFilter: "Nothing matched the search.",
    saveFailed: "Could not save",
    deleteFailed: "Could not delete",
    viewOnly: "View only",
    slugImmutable: "Slug cannot be changed",
    slugHint: "Latin letters, digits, hyphen",
    noDescription: "No description",
    emptyParen: "(empty)",
    authRequired: "Sign-in required",
    unsavedLeave: {
      title: "Unsaved changes",
      body: "You have unsaved changes. Save them before leaving?",
      confirm: "Save",
      discard: "Don't save",
    },
  },

  theme: {
    light: "Light",
    dark: "Dark",
    portracker: "Portracker",
    ariaLabel: "Color theme",
  },

  language: {
    en: "English",
    ru: "Русский",
    label: "Language",
    hint: "UI language for labels and messages",
  },

  roles: {
    superadmin: "Superadmin",
    admin: "Admin",
    user: "User",
  },

  nav: {
    groups: {
      work: "Create",
      integrations: "Integrations",
      analytics: "Analytics & diagnostics",
      administration: "Administration",
      help: "Help",
    },
    items: {
      agents: "Agents",
      runs: "Agent runs",
      schedules: "Schedules",
      tools: "Tools",
      skills: "Skills",
      mcp: "MCP",
      overview: "Overview",
      users: "Users & roles",
      doctor: "Doctor",
      notifications: "Notifications",
      llmProviders: "LLM providers",
      serviceKeys: "Service keys",
      packs: "Plugin packs (beta)",
      settings: "Settings",
      docs: "Docs",
      about: "About",
    },
    badges: {
      drafts: "drafts",
      failedRuns: "failed runs",
      disabledMcp: "disabled connections",
    },
  },

  userMenu: {
    theme: "Theme",
    language: "Language",
    settings: "Settings",
    about: "About",
    docs: "Docs",
    logout: "Log out",
  },

  viewToggle: {
    cards: "Cards",
    table: "Table",
  },

  login: {
    title: "ai-agents",
    subtitle: "Agent control plane",
    loginFailed: "Sign-in failed",
    loginKeycloak: "Sign in with Keycloak",
    cookieHint:
      "Uses a cookie session. An Keycloak account is required for access.",
  },

  about: {
    title: "About",
    subtitle: "ai-agents agent control plane",
    version: "Version {{version}}",
    blurb: [
      "ai-agents is the ai-agents control plane for building, publishing, and running LLM agents. The backend is FastAPI with LangGraph orchestration; the SPA administers agents, skills, HTTP/MCP tools, and service keys.",
      "People sign in via Keycloak (Keycloak OIDC, BFF cookie). Machines use Bearer service keys or MCP keys with scoped allowlists. Runs stream events over SSE.",
      "LLM inference goes to an external OpenAI-compatible endpoint (for example LM Studio in the lab). App pods do not attach GPUs.",
    ],
    stackTitle: "Stack",
    stack: [
      "FastAPI + LangGraph + langchain-openai",
      "PostgreSQL (Alembic migrations)",
      "React + TypeScript + Mantine",
      "Keycloak OIDC (Keycloak) + service API keys",
      "Traefik / Argo CD / Kustomize / SOPS",
    ],
    linksTitle: "Links",
    links: {
      docs: "In-app docs",
      api: "OpenAPI / Swagger",
      agentsGuide: "Agents, skills & tools",
      externalApi: "External API & MCP",
    },
  },

  docs: {
    title: "Documentation",
    subtitle: "Practical guides for the control plane",
    cards: {
      agentsSkillsTools: {
        title: "Agents, skills & tools",
        summary:
          "Recommended build order: tools → skills → agent → test → publish. Builtin and HTTP tools, skills.sh import, stale badges.",
        bodyMd: `# Agents, skills & tools

Practical UI/API guide. Field contract: OpenAPI / \`docs/API.md\`.

Roles: \`admin\` and \`superadmin\` create and publish. Role \`user\` only views and tests **published shared** agents.

Recommended order:

\`\`\`text
1. Tools (what the agent can call)
2. Skills (how to act — SKILL.md)
3. Agent (prompt + tools/skills) → test → publish
\`\`\`

## 1. Tools

A tool is an action the model may call during a run (calculator, HTTP API, remote MCP tool).

UI: **Tools** (\`/tools\`).

### Builtin

Always available (bind by name): \`calculator\`, \`now\`, \`get_server_time\`. No create step — enable them in the agent editor.

### Custom HTTP tool

UI: **Tools** → Create (or AI panel → form mode). Fill slug, name/description, method + URL, parameters, query/headers/body templates, timeout 1…60 s.

Rules:

- Placeholders only in path/query, not host.
- Only \`http(s)\`; private/loopback/metadata blocked (SSRF guard).
- Put secrets in \`headers\`; API returns \`header_names\` only.
- After save, use **Test** with sample \`params\`.

Name in \`agents.tools\` = **slug**. Custom tool edits apply to **next runs immediately** without republish. Disabled/deleted tools cannot be bound or republished (\`422\`); delete detaches from all agents.

### External MCP tools

1. UI → **MCP** → **Connections** → create (\`url\`, optional \`Authorization\` headers).
2. **Test** — refresh tool list.
3. In the agent, bind \`mcp:<connection-slug>:<tool-name>\` (e.g. \`mcp:internal-docs:search\`).

stdio MCP is not supported (Streamable HTTP only).

## 2. Skills

A skill is \`SKILL.md\` text appended to the system prompt at run time — not executable code.

UI: **Skills** (\`/skills\`).

- Manual: name/description/content; slug optional (from name). Source \`manual\` can be patched later.
- Import from \`https://skills.sh/<owner>/<repo>/<skill>\` (repeat import updates same \`source_id\`).
- Local import: pick \`.md\` / \`SKILL.md\` or folder — browser reads files and posts \`entries\` (not a Windows path to the server).

On **publish**, skill bodies are snapshotted. At run time bodies are **live from DB**; editing a skill applies to the next run and may show a stale badge until republish.

## 3. Agents

Agent = system prompt + tools/skills + optional LLM/limits. Runs require a **published** agent: prompt/LLM/limits from version snapshot; skill/tool bodies live.

1. Name, slug (\`^[a-z0-9][a-z0-9-]{1,62}$\`, immutable after create).
2. System prompt (required for \`kind=preset\`).
3. Select tools (builtin / custom / \`mcp:…\`) and skills.
4. Optional model/temperature (empty = project active provider), \`max_steps\`, \`timeout_seconds\`.
5. Save → **draft** → test run → **Publish**.
   - \`private\` — owner (+ superadmin);
   - \`shared\` — visible to services and \`user\` role; on external **MCP** (\`/mcp\`) only if slug is on the key allowlist.

| Change | Needs publish? |
|---|---|
| system prompt, LLM/limits, kind | **yes** |
| skill/tool list on agent | preferred (snapshot); resolve is live |
| skill body / custom tool URL/headers | **no** — next run; stale badges |

Archive: \`DELETE\` — runs forbidden, hidden from lists. Purge forever only from archive.

## Checklist before external handoff

1. Test run in UI or \`POST /v1/runs\` + SSE.
2. Confirm tools fire (\`tool.call\` / \`tool.result\`).
3. Publish \`shared\` if needed outside.
4. For MCP: add slug to key allowlist; verify client \`tools/list\`.

See also: External API guide.`,
      },
      externalApi: {
        title: "External API & MCP",
        summary:
          "Connect apps via REST Bearer keys or MCP Streamable HTTP. Lab/prod URLs, SSE events, allowlists.",
        bodyMd: `# Connect an external app to ai-agents

Full contract: OpenAPI / \`docs/API.md\`.

| Path | When to choose |
|---|---|
| **REST \`/v1/*\`** + Bearer | your app, batch, event stream, agent CRUD |
| **MCP \`/mcp\`** | Cursor, Claude Desktop/Code, thin MCP clients |

Base URLs:

| Contour | URL |
|---|---|
| Lab/work | \`https://ai-agents-dev.example.com\` |
| Prod | \`https://ai-agents.example.com\` |
| Local API | \`http://localhost:8096\` |

## 1. REST (service key)

1. Sign in as **superadmin**.
2. **Service keys** → create with scopes (\`runs:read/write\`, \`agents:read/write\`, \`admin\`…).
3. Key is shown **once** — store in app secrets.

\`\`\`http
Authorization: Bearer <SERVICE_API_KEY>
Content-Type: application/json
\`\`\`

Minimal flow:

1. \`GET /v1/agents?scope=shared\`
2. \`POST /v1/runs\` with \`{ agent_id, input, metadata }\` → \`run_id\`
3. Stream \`GET /v1/runs/{id}/events\` or poll \`GET /v1/runs/{id}\`
4. Cancel: \`POST /v1/runs/{id}/cancel\`

SSE events: \`run.started\`, \`message.delta\`, \`tool.call\` / \`tool.result\`, \`run.completed\` / \`run.failed\` / \`run.cancelled\`. Resume with \`after=<seq>\`.

Constraints:

- Only **published** agents (\`409\` otherwise).
- Service key sees others only if \`shared\` + \`published\`.
- \`agent_id\` is slug or UUID; invisible run → \`404\` (not \`403\`).

OpenAPI: \`{BASE}/docs\` → Authorize → \`ServiceBearer\`.

## 2. Shared MCP (IDE / thin clients)

ai-agents is an MCP server (Streamable HTTP). One endpoint; clients use different Bearer keys with **agent allowlists** (\`agent_slugs\`). Only \`published\` + \`shared\` from allowlist appear. Empty allowlist → no tools.

1. UI → **MCP** → **Servers** (superadmin) → create + allowlist → copy \`mcp-ag-…\` once.
2. Endpoint: \`{PUBLIC_URL}/mcp\`.

Client snippet:

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

Tools: \`name\` = agent slug, argument \`prompt\` (string). Tool call = internal \`POST /v1/runs\`; client gets final text.

Owner checklist: create agent → publish \`shared\` → add slug to MCP key allowlist.

## 3. Do not confuse directions

| Direction | Meaning |
|---|---|
| **MCP outbound** (\`/mcp\`, \`mcp-ag-…\`) | external clients call **our** agents |
| **MCP inbound** (\`/v1/mcp-connections\`) | **our** agents call remote MCP tools |

## Integration checklist

- [ ] Contour + \`BASE\` chosen
- [ ] Service or MCP key stored in secrets
- [ ] Agents published \`shared\` and on allowlist if MCP
- [ ] Smoke: REST run + SSE **or** MCP \`tools/list\` / tool call
- [ ] REST \`metadata\` includes source for ops
- [ ] Daily run limit applies to human \`user\` role only`,
      },
      apiContract: {
        title: "API overview",
        summary:
          "Short map of /v1 runs, agents, tools, skills, MCP, assist, and auth models.",
        bodyMd: `# API overview

Canonical field schemas live in OpenAPI (\`{BASE}/docs\`) and \`docs/API.md\`. This page is a map for UI users.

## Auth

| Principal | How |
|---|---|
| Person (SPA) | Keycloak OIDC → BFF cookie; CSRF header \`X-Requested-With: ai-agents-ui\` |
| Machine | \`Authorization: Bearer\` service key (\`SERVICE_API_KEYS\` or DB key + scopes) |
| MCP client | Bearer \`mcp-ag-…\` on \`POST /mcp\` |

## Core resources

| Area | Prefix | Notes |
|---|---|---|
| Agents | \`/v1/agents\` | scopes \`shared\` / \`owned\` / \`archived\` / \`all\`; publish, clone, rollback |
| Runs | \`/v1/runs\` | create, get, cancel; SSE \`/events\` |
| Tools | \`/v1/tools\` | builtin + custom HTTP; test invoke |
| Skills | \`/v1/skills\` | CRUD manual; import URL / local |
| MCP connections | \`/v1/mcp-connections\` | inbound tools for agents |
| MCP servers | \`/api/admin/mcp-servers\` | outbound keys + allowlist (superadmin) |
| Service keys | \`/api/admin/service-keys\` | create / revoke |
| LLM providers | admin LLM settings | active OpenAI-compatible endpoint |
| Assist | \`/v1/assist/*\` | form fill / advice using active LLM |
| Stats | \`/v1/stats/overview\` | runs/tools/API aggregates |

## Run lifecycle

\`queued\` → \`running\` → \`succeeded\` | \`failed\` | \`cancelled\`.

Create body: \`{ "agent_id": "<slug|uuid>", "input": "...", "metadata": {} }\`.

Prefer SSE for UIs; poll for simple jobs. Terminal statuses stop the event stream.

## Visibility & publish

- Draft/archived agents cannot be run externally (\`409\`).
- \`private\` vs \`shared\` controls who sees the agent beyond the owner.
- External MCP and service keys only list \`published\` + \`shared\` (plus MCP allowlist).

## Errors (typical)

| Code | Meaning |
|---|---|
| \`401\` / \`403\` | missing/forbidden auth or role |
| \`404\` | invisible or missing resource (often for foreign runs) |
| \`409\` | agent not published / conflict |
| \`422\` | validation (dead tool slug, bad \`mcp:…\`) |

For request/response examples see the External API guide and OpenAPI.`,
      },
    },
  },

  settingsPrefs: {
    title: "Settings",
    languageSection: "Language",
    languageDescription: "Choose the interface language. Changes apply immediately.",
    themeSection: "Theme",
    themeDescription: "Light, dark, or Portracker appearance for the SPA.",
  },

  errorBoundary: {
    title: "Interface error",
    home: "Go to home",
  },

  ai-agentsId: {
    label: "Keycloak user",
    description: "Search by login, name, or email; list loads more on scroll",
    placeholder: "Select a user",
    searchPlaceholder: "Search Keycloak…",
    disabledInDirectory: "disabled in Keycloak",
    loading: "Loading…",
    noneFound: "No one found",
    scrollMore: "Scroll to load more",
    endOfList: "End of list",
    selected: "Selected: {{sub}}",
    catalogUnavailable: "Keycloak catalog unavailable",
  },

  commandPalette: {
    placeholder: "Agent, tool, run, or section…",
    empty: "Nothing found",
    loading: "Loading…",
    groups: {
      sections: "Sections",
      agents: "Agents",
      tools: "Tools",
      recentRuns: "Recent runs",
    },
    toolHintCustom: "custom HTTP tool",
    toolHintBuiltin: "builtin",
    footer: "↑ ↓ — select, Enter — open",
  },

  assist: {
    title: "AI assistant",
    ariaLabel: "AI assistant",
    modelHint:
      "Model — active LLM provider (same as test runs). Section: {{target}}",
    modes: {
      form: { label: "Fill", hint: "Generate values for the current form fields" },
      advice: { label: "Advise", hint: "How to complete a step in the service" },
      review: { label: "Review", hint: "Review the current configuration" },
      test: { label: "Test", hint: "How to verify: prompt, expected events" },
    },
    formRequired:
      " — open a page with a form (agent, tool, skill, MCP, LLM)",
    emptyHint:
      "Describe what you need in words: “weather agent for Example with an HTTP tool”, “why the agent fails on step 4”, “how to issue an MCP key for Cursor”.",
    you: "You",
    assistant: "Assistant",
    fieldsCount: "fields: {{count}}",
    applyToForm: "Apply to form",
    thinking: "Thinking…",
    placeholderForm: "Describe what to fill in the form…",
    placeholderAsk: "Ask a question about the service…",
    enterHint: "Enter — send, Shift+Enter — newline",
    ask: "Ask",
    clearHistory: "Clear chat history",
    appliedNotice: "Form fields filled — review and save",
    pageSearchApplied: "Page search updated",
    pageSearchAndFieldsApplied: "Search and form updated — review and save",
    unexpectedFields:
      "The model returned fields that do not apply here — only the search was updated.",
    targets: {
      agent: "agent",
      tool: "tool",
      llm: "LLM provider",
      "mcp-connection": "MCP connection",
      "mcp-server": "MCP server",
      skill: "skill",
      user: "user",
      "service-keys": "service API keys",
      general: "general question",
    },
  },

  agents: {
    title: "Agents",
    add: "Add",
    scopes: {
      all: "All",
      shared: "Shared",
      owned: "Mine",
      archived: "Archive",
    },
    staleFilter: {
      all: "All",
      stale: "Stale",
    },
    emptyFilter: "Nothing matched the search.",
    visibility: {
      private: "personal",
      shared: "shared",
    },
    staleSkills: "skills",
    staleSkillsTitle: "Skills changed after publication",
    staleTools: "tools",
    staleToolsTitle: "Tools changed after publication",
    empty: "No agents. Click “Add” to create the first one.",
    emptyArchive:
      "Archive is empty. Agents land here after “Archive”; you can delete permanently from the card.",
    emptyStale:
      "No agents with stale skills or tools relative to the published snapshot.",
    noTools: "no tools",
    assistNeedWrite: "Creating agents requires the admin role",
    assistDraftFailed: "Could not save the assistant draft — try again from the agent editor",
    columns: {
      name: "Name",
      tools: "Tools",
      visibility: "Visibility",
      status: "Status",
      updated: "Updated",
    },
    runs: "Runs",
  },

  schedules: {
    title: "Schedules",
    add: "Add schedule",
    empty: "No schedules yet.",
    newTitle: "New schedule",
    editTitle: "Edit schedule",
    name: "Name",
    agent: "Agent",
    cron: "Cron",
    cronHint: "5 fields: minute hour day month weekday",
    timezone: "Timezone",
    input: "Input",
    enabled: "Enabled",
    disabled: "Disabled",
    enable: "Enable",
    disable: "Disable",
    runNow: "Run now",
    deleteConfirm: "Delete schedule “{{name}}”?",
    columns: {
      name: "Name",
      agent: "Agent",
      cron: "Cron",
      timezone: "Timezone",
      next: "Next run",
      last: "Last run",
      actions: "Actions",
    },
  },

  runs: {
    title: "Runs",
    filters: {
      status: "Status",
      statusAny: "any",
      agent: "Agent (id or slug)",
      agentPlaceholder: "agent identifier",
    },
    columns: {
      run: "Run",
      agent: "Agent",
      version: "Version",
      status: "Status",
      created: "Created",
      finished: "Finished",
    },
    empty: "No runs.",
    compare: "Compare",
    selectRun: "Select run for comparison",
    statuses: {
      queued: "queued",
      running: "running",
      waiting_approval: "waiting approval",
      succeeded: "succeeded",
      failed: "failed",
      cancelled: "cancelled",
    },
  },

  runCompare: {
    title: "Run comparison",
    left: "Left run",
    right: "Right run",
    submit: "Compare",
    pickTwo: "Pick two runs to compare.",
    diffTitle: "Harness diff",
    field: "Field",
    leftColumn: "Left",
    rightColumn: "Right",
    askAssistant: "Ask the assistant",
    openAgent: "Open agent",
    openRun: "Open run",
    back: "Back to runs",
    noDiff: "no differences",
    differentAgents: "Attention: the runs belong to different agents.",
    assistPrompt:
      "Compare two runs of agent {{agent}}.\nLeft {{left}}: {{leftDigest}}\nRight {{right}}: {{rightDigest}}\nDifferences:\n{{diff}}\n{{differentAgents}}\nSuggest what to change in system_prompt, tools, and skills to make behavior more stable. Return only agent form fields.",
  },

  runDetail: {
    title: "Run",
    breadcrumb: "Runs",
    notFound: "Run not found",
    noData: "No data",
    backToList: "Back to runs",
    backShort: "Back to list",
    repeat: "Repeat",
    repeatTitle: "Run the same input with the same agent",
    cancel: "Cancel",
    params: "Parameters",
    agent: "Agent:",
    version: "Version:",
    created: "Created:",
    started: "Started:",
    finished: "Finished:",
    input: "Input",
    metadata: "Metadata",
    result: "Result",
    emptyOutput: "Empty response",
    events: "Events",
    eventsReceived: "received: {{count}}",
    eventsEmpty: "Stream is empty.",
    harness: "Harness",
    harnessHash: "Fingerprint",
    harnessModel: "Model",
    harnessLimits: "Limits",
    harnessTools: "Tools",
    harnessSkills: "Skills",
    harnessMcp: "MCP",
    harnessUnavailable: "Snapshot is unavailable for runs created before this feature.",
    showHarness: "JSON",
    harnessTitle: "Run harness snapshot",
    close: "Close",
    digest: "Trajectory summary",
    digestSteps: "Steps",
    digestDuration: "Duration",
    digestEvents: "Events",
    digestOutputChars: "Output chars",
    digestNoTools: "No tool calls.",
    digestToolCalls: "Tool calls",
    digestTool: "Tool",
    digestCalls: "Calls",
    digestErrors: "Errors",
    digestUnfinished: "Unfinished tool calls: {{count}}",
    digestUnavailable: "Digest is unavailable.",
    digestTokens: "Tokens (prompt / completion / total)",
    attempts: "Attempts",
    failureKind: "Failure kind",
    parent: "Parent run:",
    depth: "Depth",
    children: "Sub-agent runs",
    noChildren: "No sub-agent runs.",
    downloadTranscript: "Download transcript",
    transcriptArchived: "Transcript archived; the digest is still available.",
    approvalRequired: "Approval required for a mutating tool",
    approvalTool: "Tool",
    approvalInput: "Input",
    approve: "Approve",
    reject: "Reject",
    approvalError: "Approval failed",
  },

  tools: {
    title: "Tools",
    add: "Add",
    newTitle: "New tool",
    editTitle: "Tool: {{name}}",
    aiTitle: "AI autofill",
    aiHint:
      "Describe the tool in words — the LLM fills URL, method, parameters, and body template. Header secrets stay empty.",
    aiPlaceholder: "Example: city weather forecast via open-meteo",
    fillFields: "Fill fields",
    describeRequired: "Describe the tool in at least one phrase",
    noFieldsFromModel: "The model suggested no fields applicable to this form",
    nameRequired: "Enter the tool name",
    slugRequired: "Enter the tool slug",
    urlRequired: "Enter the tool URL",
    paramNameRequired: "Every parameter must have a name",
    saved: "Tool “{{name}}” saved",
    created: "Tool “{{name}}” created",
    deleted: "“{{name}}” deleted",
    deletedDetached: "“{{name}}” deleted and detached from agents: {{agents}}",
    method: "Method",
    url: "URL",
    urlHint: "Template: {param} in the path is URL-encoded",
    headers: "Headers",
    headersHintCreate: "One header per line: K: V",
    headersHintEditEmpty: "Leave empty to keep; otherwise set headers (K: V)",
    headersHintEditSaved:
      "Saved: {{names}}. Leave empty to keep; otherwise replace entirely (K: V)",
    headersKeepPlaceholder: "leave empty = keep",
    query: "Query",
    queryHint: "One parameter per line: K: V",
    bodyTemplate: "body_template",
    bodyTemplateHint: "JSON request body template (for POST/PUT/PATCH)",
    enabled: "Enabled",
    on: "on",
    off: "off",
    enabledLong: "enabled",
    disabledLong: "disabled",
    parameters: "Parameters",
    addParam: "Add parameter",
    noParams: "No parameters. Add those the agent will pass to the tool.",
    paramName: "Name",
    paramType: "Type",
    paramRequired: "Required",
    paramEnumHint: "Comma-separated values; empty — no restriction",
    schemaTitle: "Schema: {{name}}",
    schemaShort: "Schema",
    schemaParams: "Parameter schema",
    testTitle: "Test: {{name}}",
    testTitleFallback: "Test tool",
    testParams: "Parameters (JSON)",
    testParamsHint: "Object with call parameters",
    testInvalidJson: "Parameters must be valid JSON",
    testExpectObject: "Expected a JSON object with parameters",
    emptyResponse: "(empty response)",
    deleteTitle: "Delete tool?",
    deleteBody: "“{{name}}” will be deleted permanently.",
    deleteInUse: "Used in agents: {{total}}",
    draftAgent: "{{slug}} (draft)",
    publishedAgent: "{{slug}} (v{{version}})",
    builtinSection: "Builtin",
    customSection: "Custom tools",
    showDetails: "Show URL",
    hideDetails: "Hide URL",
    customEmpty: "No custom tools yet — create an HTTP tool without code.",
    emptyFilter: "Nothing matched the search.",
    builtinEmpty: "No builtin tools registered.",
    sourceCustom: "custom HTTP",
    sourceBuiltin: "builtin",
    alwaysAvailable: "always available",
    paramsShort: "{{count}} params",
    deleteChecking: "Checking which agents use this tool…",
    deleteDetachHint: "The tool will be automatically removed from these agents:",
    deleteUnused: "No agent uses this tool.",
    runTest: "Run",
    urlPlaceholder: "https://api.example.com/items/{id}",
    authPlaceholder: "Authorization: Bearer …",
    columns: {
      name: "Name",
      source: "Source",
      methodUrl: "Method and URL",
      parameters: "Parameters",
      status: "Status",
    },
  },

  skills: {
    title: "Skills",
    add: "Add",
    addTitle: "Add skill",
    editTitle: "Skill: {{name}}",
    detailTitle: "Skill",
    intro:
      "A skill is a SKILL.md with procedural instructions. Attach it on the agent card; it is injected into the system prompt at run time.",
    filterPlaceholder: "Filter by name, slug, description",
    empty: "No skills imported.",
    emptyFilter: "Nothing matched the search.",
    tabs: {
      manual: "Custom skill",
      import: "skills.sh",
      local: "From computer",
    },
    aiTitle: "Generate with AI",
    aiHint:
      "Describe the skill in words — the LLM fills name, slug, description, and SKILL.md (When to use, Instructions, Example, Checklist).",
    aiPlaceholder:
      "Example: pull-request review skill — what to check, in what order, which criteria",
    describeRequired: "Describe the skill in at least one phrase",
    noFieldsFromModel: "The model suggested no skill fields",
    nameRequired: "Enter the skill name",
    contentRequired: "Add SKILL.md — manually or generate with AI",
    slugHint: "Latin letters, digits, hyphen; empty — from name",
    contentLabel: "SKILL.md",
    contentHint:
      "YAML frontmatter + sections; stored as a skill and injected into the agent prompt",
    saved: "Skill “{{name}}” saved",
    created: "Skill “{{name}}” created",
    deleted: "Skill “{{name}}” deleted",
    imported: "Skill “{{name}}” imported",
    importStatsCreated: "created: {{count}}",
    importStatsUpdated: "updated: {{count}}",
    importStatsSkipped: "skipped: {{count}}",
    importMulti: "Skill import ({{parts}}): {{names}}",
    importSingle: "Skill “{{name}}” imported ({{parts}})",
    importUrlTitle: "Import from skills.sh",
    importUrlHint:
      "Find a skill on skills.sh, copy a link like https://skills.sh/<owner>/<repo>/<skill>, and paste below.",
    importUrlLabel: "Skill URL",
    importUrlRequired: "Enter a skills.sh skill URL",
    importButton: "Import",
    importFailed: "Import failed",
    localTitle: "From your computer",
    localHint:
      "Pick a SKILL.md or skill folder, review the file list, then click Import. Files are read in the browser — no server path needed.",
    pickFile: "Choose file",
    pickFolder: "Choose folder",
    readyToImport: "Ready to import",
    selectedFiles:
      "Selected files: {{count}}. Import starts only after confirmation.",
    noSkillMd:
      "Selection has no SKILL.md / .md — pick a skill file or a folder that contains one",
    pickFirst: "Choose a file or folder first",
    deleteTitle: "Delete skill?",
    deleteBody:
      "“{{name}}” will be deleted. Agents that reference it will lose these instructions after the next publish.",
    installed: "Installed",
    source: "Source",
    content: "Content",
    filesCount: "Files ({{count}})",
    noExtraFiles: "No additional files.",
  },

  mcp: {
    title: "MCP",
    addServer: "Server",
    addConnection: "Connection",
    tabs: {
      servers: "Servers (outbound)",
      connections: "Connections (inbound)",
    },
    serversIntro:
      "Agents with status “published” and visibility “shared” are available to external MCP clients (Cursor, Claude Desktop) as tools. One key = one client.",
    serversEmpty: "No MCP servers.",
    connectionsEmpty: "No MCP connections.",
    connectionsIntro:
      "Inbound connections expose remote MCP tools to agents as mcp:<slug>:<tool>.",
    newServer: "New MCP server",
    editServer: "Edit MCP server",
    newConnection: "New connection",
    editConnection: "Edit connection",
    serverHintCreate:
      "External client label. After create you stay here: copy the client JSON (key shown once). Empty allowlists — client sees nothing.",
    serverHintEdit:
      "Allowlists for this key (agents / tools / skills). Below — client JSON; “New key” rotates the secret.",
    agentsAllowlist: "Agents (allowlist)",
    agentsAllowlistHint:
      "Published + shared experts (full run + LLM). Empty — no agents.",
    toolsAllowlist: "Tools (allowlist)",
    toolsAllowlistHint:
      "Atomic tools without agent LLM (MCP name tool__slug). Empty — none.",
    skillsAllowlist: "Skills (allowlist)",
    skillsAllowlistHint:
      "Expose get_skill for these slugs. Empty — get_skill absent.",
    noPublishedShared: "No published shared agents",
    noTools: "No tools",
    noSkills: "No skills",
    assistServerHint:
      "Fill an MCP server for Cursor on a laptop: short slug and clear name",
    headersJson: "Headers (JSON)",
    headersKeep: "Leave empty to keep saved headers",
    headersExample: 'e.g. {"Authorization": "Bearer …"}',
    timeoutSec: "Timeout, s",
    enabledSwitch: "Enabled",
    active: "active",
    inactive: "disabled",
    enabledShort: "enabled",
    disabledShort: "disabled",
    allowlistEmpty: "allowlist empty",
    noHeaders: "no headers",
    notTested: "not tested",
    toolsCached: "tools: {{count}}",
    newKey: "New key",
    enable: "Enable",
    disable: "Disable",
    check: "Test",
    keyOnce:
      "The key is shown once — save it in the client config now.",
    keyNotShown:
      "The secret is not stored. Create a new key to get a ready-to-paste client config.",
    keyRotated: "New key issued — copy the config",
    copyConfig: "Copy config",
    clientConfigTitle: "Client config (JSON)",
    serverCreated: "MCP server “{{name}}” created — copy the key",
    serverUpdated: "MCP server “{{name}}” updated",
    serverDeleted: "MCP server “{{name}}” deleted",
    connectionSaved: "Connection saved",
    connectionCreated: "Connection created",
    connectionDeleted: "Connection deleted",
    connectionDeletedDetached:
      "Connection deleted; detached from agents: {{agents}}",
    headersError: "Headers: {{message}}",
    testOk: "Connection “{{slug}}”: {{count}} tools",
    testFail: "Connection “{{slug}}” unavailable",
    noServerFields: "The model suggested no MCP server fields",
    noConnectionFields: "The model suggested no MCP connection fields",
    assistHintServers:
      "One key = one client; agent_slugs = allowlist published+shared",
    assistHintConnections: "Tools available to agents as mcp:<slug>:<tool>",
    columns: {
      name: "Name",
      slug: "slug",
      agents: "Agents",
      status: "Status",
      used: "Last used",
      url: "URL",
      tools: "Tools",
      headers: "Headers",
    },
    presets: {
      cursor: {
        label: "Cursor",
        name: "Cursor (workplace)",
        description: "Key for Cursor IDE on this workstation",
      },
      claudeDesktop: {
        label: "Claude Desktop",
        name: "Claude Desktop",
        description: "Key for Claude Desktop",
      },
      ciBot: {
        label: "CI / bot",
        name: "CI / automation",
        description: "Service MCP client for CI or a bot",
      },
    },
    namePlaceholderServer: "Cursor (laptop)",
    fillViaAi: "Fill with AI",
    authTemplate: "Authorization template",
    configPreviewTitle: "Sample client config (placeholder key until create)",
    connectionUrlHint:
      "After save, tools are available to agents as mcp:<slug>:<tool>.",
    headersCount: "headers: {{count}}",
    headersList: "headers: {{names}}",
  },

  packs: {
    title: "Plugin packs (beta)",
    refresh: "Refresh",
    add: "Add pack",
    save: "Save pack",
    manifest: "Manifest JSON",
    importHint:
      "Paste a JSON manifest. Agents are preset-only; tools/skills must already exist. YAML is supported for code-shipped packs.",
    deleteConfirm: "Delete custom pack “{{name}}”? Installed agents remain.",
    empty: "No packs registered in this build.",
    notInstalled: "not installed",
    dryRun: "Dry run",
    install: "Install",
    dryRunHint: "Preview only: nothing was written.",
    installDone: "Pack installed.",
    alreadyInstalled: "This pack version is already installed.",
    noChanges: "No agent changes.",
    agents: "Agents",
    skills: "Skills",
    tools: "Tools",
    entity: "Entity",
    ref: "Ref",
    action: "Action",
    columns: {
      name: "Pack",
      description: "Description",
      refs: "Contents",
      installed: "Installed",
      actions: "Actions",
    },
    actions: {
      create: "create",
      update: "update",
      noop: "noop",
    },
    sources: {
      code: "build",
      custom: "custom",
    },
  },

  notifications: {
    title: "Notifications",
    add: "Add channel",
    refresh: "Refresh",
    empty: "No channels yet.",
    newTitle: "New channel",
    editTitle: "Edit channel",
    name: "Name",
    kind: "Kind",
    url: "Webhook URL",
    chatId: "Telegram chat id",
    secret: "Signing secret",
    secretHint: "Used for X-Ai-Agents-Signature; not shown after save",
    enabled: "Enabled",
    disabled: "Disabled",
    secretConfigured: "secret set",
    deliveries: "Recent deliveries",
    noDeliveries: "No deliveries yet.",
    deleteConfirm: "Delete channel “{{name}}”?",
    columns: {
      name: "Name",
      kind: "Kind",
      target: "Target",
      status: "Status",
      actions: "Actions",
      run: "Run",
      channel: "Channel",
      attempts: "Attempts",
      created: "Created",
      error: "Error",
    },
    statuses: {
      pending: "pending",
      sent: "sent",
      failed: "failed",
    },
  },

  users: {
    title: "Users & roles",
    add: "Add",
    addTitle: "Add user",
    intro:
      "Role user — view and test published shared agents only; daily run limit is set here or via USER_DAILY_RUN_LIMIT. Role admin — CRUD and publish own agents/skills, no access or settings management. Only a bootstrap account (SUPERADMIN_EMAILS) can grant or revoke superadmin; other superadmins manage admin/user only.",
    columns: {
      user: "User",
      role: "Role",
      changeRole: "Change role",
      dailyLimit: "Limit / day",
      runsToday: "Runs today",
      login: "Sign-in",
    },
    roleOptions: {
      superadmin: "Superadmin — everything",
      admin: "Admin — own agents/skills",
      user: "User — view and test",
    },
    roleSelect: "Role",
    roleSuperadminHint:
      "Only a bootstrap account (SUPERADMIN_EMAILS) can assign superadmins",
    dailyLimit: "Daily run limit",
    dailyLimitHint: "Empty — value from env",
    dailyLimitPlaceholder: "from env",
    updated: "User {{id}} updated",
    created: "User {{id}} added",
    noUserFields: "The model suggested no user fields",
    superadminOnlyBootstrap:
      "Only a bootstrap account (SUPERADMIN_EMAILS) can assign superadmins",
  },

  doctor: {
    title: "Platform doctor",
    refresh: "Refresh",
    ok: "Ready",
    failed: "Issues found",
    check: "Check",
    status: "Status",
    message: "Message",
    details: "Details",
    showJson: "JSON",
    jsonTitle: "Raw check details",
    fields: {
      current: "revision",
      heads: "expected",
      model: "model",
      models: "models",
      oidc: "OIDC",
      service_keys: "service keys",
      path: "path",
      writable: "writable",
      free_gb: "free GiB",
      queued: "queued",
      running: "running",
      total: "total",
      oldest_seconds: "oldest s",
      approvals_pending: "approvals",
      per_agent: "per agent",
      last_run_seconds_ago: "last run s",
      limit_seconds: "limit s",
      pending: "pending",
      failed_24h: "failed 24h",
      by_failure_kind: "by kind",
      connections: "connections",
      errors: "errors",
    },
    statuses: {
      ok: "ok",
      warn: "warn",
      error: "error",
      skip: "skip",
    },
  },

  serviceKeys: {
    title: "Service keys",
    forbiddenTitle: "Access denied",
    forbiddenBody: "This section is available to superadmins only.",
    newKey: "New key",
    scopes: "Scopes",
    scopesHint:
      "Pick a preset or tick scopes manually. *:write = catalog CRUD; *:execute = action.",
    scopePresets: {
      label: "Preset:",
      consume: "Read & execute",
      consumeHint:
        "External app / factory: catalog, tool invoke, and runs. No CRUD or admin.",
      manage: "Catalog manage",
      manageHint: "Read, execute, and CRUD agents/tools/skills. No admin settings.",
      full: "Full access",
      fullHint: "All scopes including admin (LLM settings / machine admin).",
    },
    createKey: "Create key",
    updateChanges: "Apply changes",
    nameAndScopeRequired: "Enter a name and at least one scope",
    keyOnce: "The key is shown once — save it now.",
    empty: "No keys.",
    agentsAllowlist: "Agents (catalog)",
    toolsAllowlist: "Tools (catalog)",
    skillsAllowlist: "Skills (catalog)",
    allowlistHint:
      "Fail-closed for /v1/catalog and tool invoke: empty list denies that category.",
    scopeLabels: {
      agents_read: "Read agents",
      agents_write: "Manage agents",
      tools_read: "Read tools",
      tools_execute: "Execute tools",
      tools_write: "Manage tools",
      skills_read: "Read skills",
      skills_write: "Manage skills",
      runs_read: "Read runs",
      runs_execute: "Execute runs",
      admin: "Admin settings",
    },
    scopeHints: {
      agents_read: "List/get agents and agent section of /v1/catalog.",
      agents_write: "Create, edit, publish agents and MCP connections; AI assist for agents.",
      tools_read: "List tool specs and tools section of /v1/catalog.",
      tools_execute: "Call POST /v1/tools/…/invoke (no agent LLM). Not the same as tools:write.",
      tools_write: "Create/edit/delete custom HTTP tools (CRUD). Does not grant invoke.",
      skills_read: "Read skill content and skills section of /v1/catalog.",
      skills_write: "Create, import, edit, delete skills (CRUD).",
      runs_read: "View runs, SSE events, and usage stats.",
      runs_execute: "Start and cancel agent runs (POST /v1/runs). Legacy alias: runs:write.",
      admin: "Change LLM providers and other admin settings (full machine admin).",
    },
    columns: {
      name: "Name",
      scopes: "Scopes",
      catalog: "Catalog",
      status: "Status",
      created: "Created",
      used: "Last used",
    },
    active: "active",
    revoked: "revoked",
    revoke: "Revoke",
    restore: "Restore",
    delete: "Delete",
    deleteTitle: "Delete service key “{{name}}”?",
    deleteBody: "This permanently removes the key. Revoke only disables it; a revoked key can be restored with the same value until deleted.",
    deleted: "Key “{{name}}” deleted",
  },

  stats: {
    title: "Overview",
    since: "since {{date}}",
    windows: {
      d7: "7 days",
      d14: "14 days",
      d30: "30 days",
    },
    cards: {
      runs: "Runs",
      successRate: "Success rate",
      toolCalls: "Tool calls",
      tokens: "Tokens",
      apiRequests: "API requests",
      apiErrors: "API errors",
      apiP95: "p95 API",
    },
    runsDaily: "Runs by day",
    forPeriod: "{{count}} in period",
    statusSucceeded: "succeeded",
    statusFailed: "failed",
    statusCancelled: "cancelled",
    apiSeries: "API: requests and errors",
    seriesRequests: "requests",
    seriesErrors: "errors",
    toolsDaily: "Tool calls by day",
    seriesCalls: "calls",
    topTools: "Top tools",
    noToolCalls: "No calls yet.",
    agents: "Agents",
    noAgentRuns: "No runs yet.",
    agentColumns: {
      agent: "Agent",
      runs: "Runs",
      succeeded: "Succeeded",
      failed: "Failed",
      tokens: "Tokens",
      avgTime: "Avg time",
    },
    queue: "Queue: {{count}}",
    oldestQueued: "Oldest: {{value}}s",
    topEndpoints: "API: popular endpoints",
    noApiRequests: "No requests yet.",
    endpointColumns: {
      method: "Method",
      path: "Path",
      calls: "Calls",
      errors: "Errors",
      p95: "p95",
    },
    ms: "{{value}} ms",
    sec: "{{value}} s",
  },

  agentEditor: {
    breadcrumbNew: "New agent",
    titleNew: "New agent",
    aiTitle: "AI autofill",
    aiHint:
      "Describe the agent in words — the LLM fills name, prompt, tools, and skills. Model and limits stay yours.",
    aiPlaceholder:
      "Example: calculation helper — evaluates expressions and tells Moscow time",
    missingTools:
      "Missing tools: {{list}} — create them on the Tools page.",
    basics: "Basics",
    systemPrompt: "System prompt",
    kind: "Agent type",
    kindPreset: "Preset — normal agent",
    kindPlugin: "Plugin — developer code",
    kindPresetHint: "Prompt, tools, skills and memory run in the built-in ReAct loop.",
    kindPluginHint: "No prompt/tools: backend calls a code handler registered by name.",
    pluginName: "Plugin name",
    pluginHint: "Name from backend/app/agents/plugins.py; requires a backend build.",
    pluginAlert: "A plugin is code, not data. Only a developer can add it and rebuild the backend; the agent just points to that registered name.",
    tools: "Tools",
    toolsHint: "Tool edits apply immediately without republish",
    toolsNotFound: "No tools found",
    skills: "Skills",
    skillsHint: "Imported skills.sh skills",
    skillsNotFound: "No skills found",
    subAgents: "Sub-agents",
    subAgentsHint: "Only published agents available to you (owned or shared), except this agent.",
    memoryEnabled: "Agent memory",
    memoryHint: "Enables three built-in tools: memory_write, memory_search, memory_delete. They are not in the tools catalog; notes are isolated per agent and user.",
    memory: "Stored memory",
    memoryEmpty: "No notes yet.",
    memoryKey: "Key",
    memoryContent: "Content",
    memoryTags: "Tags",
    memoryUpdated: "Updated",
    toolsGroupBuiltinHttp: "Builtin and HTTP",
    toolsGroupOther: "Other",
    llm: "LLM",
    llmGlobalHint: "Empty means the application-wide LLM provider. Override only for a dedicated model/endpoint.",
    llmOverride: "Override LLM for this agent",
    temperature: "Temperature",
    temperatureHint: "0–1, not percent: 0 = deterministic, 1 = creative.",
    model: "Model",
    limits: "Limits",
    maxTokens: "max_tokens",
    maxAttempts: "max_attempts",
    approvalMode: "Tool call approvals",
    approvalHint: "Ask a human before tool calls: mutating = POST/PUT/PATCH/DELETE HTTP and any MCP tool; all = any tool; never = no approval. Waiting counts toward the run timeout.",
    approvalModes: {
      mutating: "Mutating only",
      all: "All tools",
      never: "No approval",
    },
    clone: "Clone",
    archive: "Archive",
    purge: "Delete forever",
    publish: "Publish",
    publishSection: "Publication",
    visibilityPrivate: "Personal",
    visibilityShared: "Shared",
    publishedVersion: "Published version: {{version}}",
    neverPublished: "Not published yet",
    versions: "Versions",
    noVersions: "No versions yet",
    versionCol: "Version",
    createdCol: "Created",
    authorCol: "Author",
    current: "current",
    rollback: "Roll back",
    testRun: "Test run",
    publishFirst: "Publish the agent first",
    input: "Input",
    defaultTestInput: "Hi! Calculate 17*4+9.",
    run: "Run",
    preflight: "Check readiness",
    preflightTitle: "Agent preflight",
    preflightOk: "Ready to run",
    preflightFailed: "Not ready",
    preflightCheck: "Check",
    preflightStatus: "Status",
    preflightMessage: "Message",
    preflightEffective: "Effective config",
    preflightModel: "Model",
    preflightBaseUrl: "Base URL",
    preflightVersionNote: "Checks the published version v{{version}}.",
    preflightClose: "Close",
    preflightChecks: {
      agent: "Agent",
      plugin: "Plugin",
      quota: "Daily quota",
      tools: "Tools",
      skills: "Skills",
      mcp: "MCP",
      llm: "LLM",
      limits: "Limits",
    },
    eventsCount: "events: {{count}}",
    runFailed: "Run finished with an error",
    nameRequired: "Enter the agent name",
    slugRequired: "Enter the agent slug",
    created: "Agent created",
    saved: "Changes saved",
    describeRequired: "Describe the agent in at least one phrase",
    filledNotice: "Fields filled — review and save",
    saveFirst: "Save the agent first",
    publishedNotice: "Agent published (visibility={{visibility}})",
    cloned: "Created copy “{{name}}”",
    rolledBack:
      "Rolled back to v{{version}}: published new version v{{published}}",
    archived: "Agent moved to archive",
    purgeOnlyArchive: "Only an archived agent can be deleted forever",
    noFieldsFromModel: "The model suggested no fields applicable to this form",
    staleSnapshotTitle: "Version snapshot is stale",
    staleSnapshotBody:
      "Skill and custom-tool changes already apply to next runs. Republishing updates snapshot{{version}} and clears the badges.",
    viewOnlyBody:
      "Role “User” can view published agents and run a test request, but cannot change them.",
    rollbackTitle: "Roll back to v{{version}}?",
    rollbackBody:
      "Configuration (prompt, skills, LLM, limits) will be taken from snapshot v{{version}}. History is not rewritten: a new version will be created and published, and the current draft content will be replaced.",
    rollbackToolsNote:
      "Tools apply live and are not rolled back in the snapshot — the agent’s current tool list remains.",
    purgeTitle: "Delete “{{name}}” forever?",
    purgeBody:
      "The agent and its version history will be removed permanently. Runs already finished stay in the log.",
    agentFallback: "agent",
  },

  llmSettings: {
    title: "LLM providers",
    addProvider: "Add provider",
    newProvider: "New provider",
    viewOnlyBody: "Only a superadmin can manage providers and the active model.",
    effectiveEndpoint: "Effective endpoint",
    sourceProvider: "active provider",
    sourceLegacy: "legacy settings",
    sourceEnv: "env",
    modelUnset: "model not set",
    keySet: " · key set",
    keyMissing: " · no key",
    effectiveHint:
      "Applies to agent runs and AI autofill when the agent has no own base_url/model.",
    empty:
      "No providers — environment variables (DEFAULT_LLM_*) are used.",
    providerName: "Provider name",
    providerNamePlaceholder: "LM Studio / vLLM / external API",
    preset: "Preset",
    presetHint: "Fills base_url and auth scheme; everything remains editable",
    presetHintShort: "Fills base_url and auth scheme",
    presetNone: "none selected",
    auth: "Authorization",
    authHeader: "Header",
    authPrefix: "Key prefix",
    authPrefixHint: "e.g. “Bearer ” or empty",
    authKeyPreview: "Sent as {{header}}: {{prefix}}<key>",
    apiKey: "API key",
    apiKeyHintLocal: "Can be left empty for local servers",
    apiKeySaved: "Key saved ({{hint}}); leave empty to keep",
    apiKeyUnset: "No key set",
    model: "Model",
    modelHint: "List comes from the provider; you can type manually",
    modelHintCreate: "After create you can pick from the provider list",
    modelPlaceholder: "Load the model list",
    fetchModels: "Fetch models",
    makeActive: "Make active",
    activeBadge: "active",
    updatedAt: "Updated: {{date}}",
    modelsFetched: "Models from “{{name}}”: {{count}}",
    providerSaved: "Provider “{{name}}” saved",
    providerActive: "Active provider: “{{name}}”",
    providerDeleted: "Provider “{{name}}” deleted",
    providerAdded: "Provider added — make it active if needed",
    noProviderFields: "The model suggested no provider fields",
    deleteTitle: "Delete provider “{{name}}”?",
    deleteBody: "The provider will be deleted permanently.",
    deleteActiveNote:
      " It is currently active: agents and autofill will fall back to env/legacy settings.",
    authTypes: {
      bearer: {
        label: "Authorization: Bearer <key>",
        short: "Bearer",
        hint: "Standard for OpenAI-compatible APIs",
      },
      custom: {
        label: "Custom header and prefix",
        short: "Custom header",
        hint: "e.g. x-api-key without prefix",
      },
      none: {
        label: "No auth",
        short: "No auth",
        hint: "Local LM Studio / Ollama",
      },
    },
    presets: {
      openaiCompat: {
        label: "OpenAI-compatible",
        note: "Any /v1 with OpenAI API (vLLM, gateways, clouds)",
      },
      lmStudio: {
        label: "LM Studio",
        note: "Local host server, no key required",
      },
      ollama: {
        label: "Ollama",
        note: "OpenAI-compatible /v1 Ollama",
      },
      anthropicGateway: {
        label: "Anthropic-compatible gateway",
        note: "Needs an OpenAI-compatible gateway: key goes to x-api-key",
      },
    },
  },
} as const;

export default en;
