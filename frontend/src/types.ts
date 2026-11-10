export type AgentKind = "preset" | "plugin";
export type AgentVisibility = "private" | "shared";
export type AgentStatus = "draft" | "published" | "archived";
export type AgentScope = "owned" | "shared" | "all" | "archived";
export type RunStatus =
  | "queued"
  | "running"
  | "waiting_approval"
  | "succeeded"
  | "failed"
  | "cancelled";

export type AppRole = "superadmin" | "admin" | "user";

export interface MeUser {
  id: string;
  email: string | null;
  /** ФИО из Keycloak (`display_name`), фолбэк — email. */
  name: string | null;
  display_name?: string | null;
  is_superadmin: boolean;
  /** bootstrap-суперадмин (SUPERADMIN_EMAILS): может назначать суперадминов. */
  can_manage_superadmins?: boolean;
  roles: string[];
  app_role?: AppRole;
  daily_run_limit?: number | null;
}

export interface Me {
  authenticated: boolean;
  user: MeUser;
}

export interface AgentLlm {
  base_url: string | null;
  model: string | null;
  temperature: number | null;
}

export interface AgentLimits {
  max_steps: number;
  timeout_seconds: number;
  max_tokens?: number;
  max_attempts?: number;
  approval_mode?: string;
}

export interface AgentOwner {
  kind: string;
  id: string;
  email: string | null;
}

export interface Agent {
  id: string;
  slug: string;
  name: string;
  description: string;
  kind: AgentKind;
  plugin_name: string | null;
  system_prompt: string;
  tools: string[];
  skills: string[];
  sub_agents?: string[];
  memory_enabled?: boolean;
  llm: AgentLlm;
  limits: AgentLimits;
  visibility: AgentVisibility;
  status: AgentStatus;
  published_version: number | null;
  /** Live skill body differs from published snapshot (runs already use live). */
  skills_stale?: boolean;
  /** Live custom-tool body differs from published snapshot. */
  tools_stale?: boolean;
  owner: AgentOwner;
  created_at: string;
  updated_at: string;
}

export interface AgentList {
  items: Agent[];
  total: number;
}

export interface AgentUpsert {
  slug: string;
  name: string;
  description: string;
  kind: AgentKind;
  plugin_name: string | null;
  system_prompt: string;
  tools: string[];
  skills: string[];
  sub_agents?: string[];
  memory_enabled?: boolean;
  llm: AgentLlm;
  limits: AgentLimits;
}

/** PATCH: те же поля, что и при создании, кроме `slug` (slug неизменяем). */
export type AgentPatch = Partial<Omit<AgentUpsert, "slug">> & {
  status?: AgentStatus;
};

export interface AgentVersion {
  id: string;
  version: number;
  created_by: string | null;
  created_at: string;
  snapshot: Record<string, unknown>;
}

export type ToolSource = "builtin" | "custom";
export type ToolMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
export type ToolParamType = "string" | "number" | "integer" | "boolean";

/** Описание инструмента в реестре агента (встроенный или свой). */
export interface ToolSpec {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  source: ToolSource;
}

export interface ToolParam {
  name: string;
  type: ToolParamType;
  description: string;
  required: boolean;
  enum: string[] | null;
}

/** Свой HTTP-инструмент (`/v1/tools/custom`). */
export interface Tool {
  id: string;
  slug: string;
  name: string;
  description: string;
  kind: string;
  method: ToolMethod;
  url: string;
  header_names: string[];
  query: Record<string, string>;
  body_template: string | null;
  content_type: string;
  parameters: ToolParam[];
  timeout_seconds: number;
  enabled: boolean;
  owner: AgentOwner;
  created_at: string;
  updated_at: string;
}

export interface ToolUpsert {
  slug: string;
  name: string;
  description: string;
  method: ToolMethod;
  url: string;
  headers: Record<string, string>;
  query: Record<string, string>;
  body_template: string | null;
  content_type: string;
  parameters: ToolParam[];
  timeout_seconds: number;
  enabled: boolean;
}

/** PATCH: те же поля, что при создании, кроме `slug` (slug неизменяем). `headers` — только если заданы. */
export type ToolPatch = Partial<Omit<ToolUpsert, "slug">>;

export interface ToolList {
  items: Tool[];
  total: number;
}

export interface ToolTestResult {
  ok: boolean;
  status: number | null;
  output: string;
}

/** Подсказка LLM для формы агента (`POST /v1/assist/agent`). */
export interface SuggestedTool {
  slug: string;
  name: string;
  description: string;
  note: string;
}

export interface AgentSuggestion {
  name: string;
  slug: string;
  description: string;
  system_prompt: string;
  tools: string[];
  skills: string[];
  new_tools: SuggestedTool[];
  notes: string;
  warnings: string[];
}

/** Подсказка LLM для формы HTTP-инструмента (`POST /v1/assist/tool`). */
export interface ToolSuggestion {
  slug: string;
  name: string;
  description: string;
  method: ToolMethod;
  url: string;
  headers: Record<string, string>;
  query: Record<string, string>;
  body_template: string | null;
  content_type: string;
  parameters: ToolParam[];
  notes: string;
  warnings: string[];
}

/** Проектные настройки LLM (`/v1/settings/llm`). Ключ наружу не отдаётся. */
export interface LLMSettings {
  base_url: string;
  model: string;
  api_key_set: boolean;
  api_key_hint: string | null;
  source: "db" | "env" | "provider";
  auth_type: LLMAuthType;
  auth_header: string;
  auth_prefix: string;
  updated_by: string | null;
  updated_at: string | null;
}

export interface LLMModelsResult {
  base_url: string;
  models: string[];
}

export interface Skill {
  id: string;
  slug: string;
  name: string;
  description: string;
  source: string;
  source_id: string | null;
  source_url: string | null;
  hash: string | null;
  created_at: string;
  updated_at: string;
}

export interface SkillFile {
  path: string;
  contents: string;
}

export interface SkillDetail extends Skill {
  content: string;
  files: SkillFile[];
}

export interface SkillList {
  items: Skill[];
  total: number;
}

/** Результат поиска по skills.sh: `url` — ссылка для импорта. */
export interface SkillSuggestion {
  name: string;
  slug: string;
  description: string;
  content: string;
  notes: string;
  warnings: string[];
}

export interface SkillSearchItem {
  url: string;
  name?: string | null;
  description?: string | null;
  source_id?: string | null;
  [key: string]: unknown;
}

export interface SkillSearchResult {
  items: SkillSearchItem[];
  total?: number;
}

export interface SkillLocalFileEntry {
  path: string;
  content: string;
}

export interface SkillLocalImportResult {
  items: Skill[];
  created: number;
  updated: number;
  skipped: { path: string; reason: string }[];
}

export interface Run {
  run_id: string;
  agent_id: string;
  agent_version: number | null;
  status: RunStatus;
  input: unknown;
  metadata: Record<string, unknown> | null;
  output: unknown;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  harness_hash: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  failure_kind: string | null;
  attempts: number | null;
  parent_run_id: string | null;
  depth: number;
  events_archived_at: string | null;
}

export interface HarnessSnapshot {
  v: number;
  agent: { slug: string; version: number };
  kind: string;
  plugin_name: string | null;
  system_prompt: string;
  tools: string[];
  skills: string[];
  sub_agents?: string[];
  llm: {
    model: string | null;
    base_url: string | null;
    temperature: number;
    auth_type: string | null;
    auth_header: string | null;
    auth_prefix: string | null;
    api_key_present: boolean;
  };
  limits: {
    max_steps: number;
    timeout_seconds: number;
    max_tokens?: number;
    max_attempts?: number;
    approval_mode?: string;
  };
  retry?: { fallback_model: string | null };
  context?: {
    max_tokens: number;
    tool_output_max_chars: number;
    skills_mode: string;
  };
  mcp: { ref: string; connection: string; tool: string }[];
  tool_defs: { slug: string; name: string }[];
  skill_defs: { slug: string; name: string }[];
}

export interface RunHarness {
  run_id: string;
  harness_hash: string | null;
  snapshot: HarnessSnapshot | null;
}

export interface RunApproval {
  id: string;
  run_id: string;
  tool: string;
  input: Record<string, unknown>;
  status: "pending" | "approved" | "rejected" | "expired";
  requested_at: string;
  resolved_at: string | null;
  resolved_by: string;
}

export type PreflightStatus = "ok" | "warn" | "error" | "skip";

export interface PreflightCheck {
  id: "agent" | "plugin" | "quota" | "tools" | "skills" | "mcp" | "llm" | "limits";
  status: PreflightStatus;
  message: string;
  details: Record<string, unknown>;
}

export interface PreflightEffective {
  agent_id: string;
  agent_version: number | null;
  model: string | null;
  base_url: string | null;
  max_steps: number;
  timeout_seconds: number;
  max_tokens: number;
  max_attempts: number;
  approval_mode: string;
  sub_agents: string[];
  tools: string[];
  skills: string[];
  mcp: string[];
}

export interface PreflightResult {
  ok: boolean;
  checks: PreflightCheck[];
  effective: PreflightEffective;
}

export interface RunCompareResult {
  left: Run;
  right: Run;
  left_digest: TrajectoryDigest;
  right_digest: TrajectoryDigest;
  diff: HarnessDiffItem[];
}

export interface HarnessDiffItem {
  field: string;
  left: unknown;
  right: unknown;
  changed: boolean;
}

export interface ToolCallDigest {
  tool: string;
  calls: number;
  errors: number;
}

export interface TrajectoryDigest {
  run_id: string;
  agent_id: string;
  agent_version: number | null;
  harness_hash: string | null;
  status: RunStatus;
  duration_ms: number | null;
  steps: number;
  events_total: number;
  tool_calls: ToolCallDigest[];
  total_tool_calls: number;
  failed_tool_calls: number;
  unfinished_tool_calls: number;
  output_chars: number;
  error: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  failure_kind: string | null;
  attempts: number | null;
}

export interface RunList {
  items: Run[];
  total: number;
}

export type RunEventName =
  | "run.started"
  | "message.delta"
  | "tool.call"
  | "tool.result"
  | "agent.step"
  | "token.usage"
  | "run.retry"
  | "run.approval_required"
  | "run.approval_resolved"
  | "subrun.started"
  | "subrun.completed"
  | "run.completed"
  | "run.failed"
  | "run.cancelled";

export interface RunEvent {
  seq: number;
  event: RunEventName | string;
  data: Record<string, unknown>;
}

export const TERMINAL_RUN_STATUSES: RunStatus[] = ["succeeded", "failed", "cancelled"];

export function isTerminalRun(status: RunStatus): boolean {
  return TERMINAL_RUN_STATUSES.includes(status);
}

export interface ServiceKey {
  id: string;
  name: string;
  scopes: string[];
  agent_slugs: string[];
  tool_slugs: string[];
  skill_slugs: string[];
  enabled: boolean;
  created_at: string;
  last_used_at: string | null;
}

export interface ServiceKeyCreated extends ServiceKey {
  key: string;
}

export const SERVICE_KEY_SCOPES = [
  "agents:read",
  "agents:write",
  "tools:read",
  "tools:execute",
  "tools:write",
  "skills:read",
  "skills:write",
  "runs:read",
  "runs:execute",
  "admin",
] as const;

export type ServiceKeyScope = (typeof SERVICE_KEY_SCOPES)[number];

/** Preset packs by trust level (least → most privilege). */
export const SERVICE_KEY_SCOPE_PRESETS = {
  /** External app / factory: catalog + invoke + runs, no CRUD. */
  consume: [
    "agents:read",
    "tools:read",
    "tools:execute",
    "skills:read",
    "runs:read",
    "runs:execute",
  ],
  /** Automations that also mutate catalog (still no admin). */
  manage: [
    "agents:read",
    "agents:write",
    "tools:read",
    "tools:execute",
    "tools:write",
    "skills:read",
    "skills:write",
    "runs:read",
    "runs:execute",
  ],
  /** Full machine access including admin settings. */
  full: [...SERVICE_KEY_SCOPES],
} as const satisfies Record<string, readonly ServiceKeyScope[]>;

export type ServiceKeyScopePreset = keyof typeof SERVICE_KEY_SCOPE_PRESETS;

export interface IdentityUser {
  sub: string;
  username: string;
  email: string | null;
  display_name: string | null;
  enabled: boolean;
}

export interface IdentityUserPage {
  items: IdentityUser[];
  has_more: boolean;
}

export interface AdminUser {
  id: string;
  email: string | null;
  display_name: string | null;
  is_superadmin: boolean;
  is_bootstrap: boolean;
  roles: string[];
  app_role: AppRole;
  daily_run_limit: number | null;
  runs_today: number;
  last_login_at: string | null;
}

export interface RunsDailyPoint {
  date: string;
  succeeded: number;
  failed: number;
  cancelled: number;
  other: number;
}

export interface ToolDailyPoint {
  date: string;
  calls: number;
}

export interface ApiDailyPoint {
  date: string;
  calls: number;
  errors: number;
}

export interface AgentUsage {
  slug: string;
  runs: number;
  succeeded: number;
  failed: number;
  success_rate: number;
  avg_duration_ms: number | null;
  tokens: number;
}

export interface ToolUsage {
  slug: string;
  calls: number;
}

export interface EndpointUsage {
  method: string;
  path: string;
  calls: number;
  errors: number;
  p95_ms: number | null;
}

export interface StatsOverview {
  days: number;
  since: string;
  runs_total: number;
  runs_succeeded: number;
  success_rate: number;
  runs_daily: RunsDailyPoint[];
  tokens_total: number;
  queued_runs: number;
  oldest_queued_seconds: number | null;
  tools_total: number;
  tools_daily: ToolDailyPoint[];
  api_total: number;
  api_errors: number;
  api_latency: { p50_ms: number | null; p95_ms: number | null };
  api_daily: ApiDailyPoint[];
  top_agents: AgentUsage[];
  top_tools: ToolUsage[];
  top_endpoints: EndpointUsage[];
}

export interface DoctorCheck {
  id: string;
  status: "ok" | "warn" | "error" | "skip";
  message: string;
  details: Record<string, unknown>;
  duration_ms: number;
}

export interface DoctorResult {
  ok: boolean;
  generated_at: string;
  checks: DoctorCheck[];
}

export interface Schedule {
  id: string;
  name: string;
  agent_slug: string;
  input: unknown;
  cron: string;
  timezone: string;
  enabled: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  last_run_id: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScheduleList {
  items: Schedule[];
  total: number;
}

export interface NotificationChannel {
  id: string;
  name: string;
  kind: "webhook" | "telegram";
  url: string | null;
  chat_id: string | null;
  enabled: boolean;
  secret_configured: boolean;
  created_at: string;
  updated_at: string;
}

export interface Delivery {
  id: string;
  run_id: string;
  channel_id: string;
  status: "pending" | "sent" | "failed";
  attempts: number;
  next_attempt_at: string | null;
  last_error: string | null;
  created_at: string;
  sent_at: string | null;
}

export interface DeliveryList {
  items: Delivery[];
  total: number;
}

export interface AgentMemory {
  id: string;
  agent_id: string;
  namespace: string;
  key: string;
  content: string;
  tags: string[];
  created_at: string;
  updated_at: string;
  expires_at: string | null;
}

export interface PackChange {
  entity: "agent";
  ref: string;
  action: "create" | "update" | "noop";
}

export interface Pack {
  name: string;
  version: string;
  description: string;
  source: "code" | "custom";
  agents: string[];
  skills: string[];
  tools: string[];
  installed_versions: string[];
}

export interface PackInstallResult {
  name: string;
  version: string;
  dry_run: boolean;
  installed: boolean;
  already_installed: boolean;
  changes: PackChange[];
}

export interface ToolUserAgent {
  slug: string;
  name: string;
  status: string;
  published_version: number | null;
}

export interface ToolUsage {
  slug: string;
  total: number;
  agents: ToolUserAgent[];
}

export interface ToolDeleteResult {
  slug: string;
  detached_agents: string[];
}

export type LLMAuthType = "bearer" | "header" | "none";

export interface LLMProvider {
  id: string;
  name: string;
  base_url: string;
  model: string;
  api_key_set: boolean;
  api_key_hint: string | null;
  auth_type: LLMAuthType;
  auth_header: string;
  auth_prefix: string;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface LLMProvidersState {
  items: LLMProvider[];
  active_id: string | null;
  effective: LLMSettings;
}

export interface McpServer {
  id: string;
  slug: string;
  name: string;
  description: string;
  enabled: boolean;
  /** Allowlist published+shared agent slugs; empty → no agents in tools/list. */
  agent_slugs: string[];
  /** Atomic tools (builtin/custom); empty → none. MCP names: tool__{slug}. */
  tool_slugs: string[];
  /** Skills for get_skill; empty → get_skill absent. */
  skill_slugs: string[];
  created_by: string;
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
  url: string;
}

export interface McpServerCreated extends McpServer {
  api_key: string;
}

export interface McpServerList {
  items: McpServer[];
  total: number;
}

export interface McpToolInfo {
  name: string;
  description: string;
}

export interface McpConnection {
  id: string;
  slug: string;
  name: string;
  description: string;
  url: string;
  header_names: string[];
  timeout_seconds: number;
  enabled: boolean;
  owner: AgentOwner;
  tools_cache: McpToolInfo[];
  tools_cached_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface McpConnectionList {
  items: McpConnection[];
  total: number;
}

export interface McpConnectionTestResult {
  ok: boolean;
  tools: McpToolInfo[];
  error: string | null;
}

export interface McpConnectionDeleteResult {
  slug: string;
  detached_agents: string[];
}

/** Auth schemes for LLM providers. UI labels come from i18n (`llmSettings.authTypes`). */
export const LLM_AUTH_TYPES: { value: LLMAuthType; label: string; hint: string }[] = [
  {
    value: "bearer",
    label: "Authorization: Bearer <key>",
    hint: "Standard OpenAI-compatible APIs",
  },
  {
    value: "header",
    label: "Custom header and prefix",
    hint: "e.g. x-api-key with empty prefix",
  },
  { value: "none", label: "No auth", hint: "Local LM Studio / Ollama" },
];

/** Provider presets: known base_url + auth; all fields editable. UI via i18n. */
export const LLM_PROVIDER_PRESETS: {
  value: string;
  label: string;
  base_url: string;
  auth_type: LLMAuthType;
  auth_header: string;
  auth_prefix: string;
  note: string;
}[] = [
  {
    value: "openai",
    label: "OpenAI-compatible",
    base_url: "",
    auth_type: "bearer",
    auth_header: "Authorization",
    auth_prefix: "Bearer ",
    note: "Any /v1 OpenAI API (vLLM, gateways, clouds)",
  },
  {
    value: "lmstudio",
    label: "LM Studio",
    base_url: "http://host.docker.internal:1234/v1",
    auth_type: "none",
    auth_header: "Authorization",
    auth_prefix: "Bearer ",
    note: "Local host server, no key required",
  },
  {
    value: "ollama",
    label: "Ollama",
    base_url: "http://host.docker.internal:11434/v1",
    auth_type: "none",
    auth_header: "Authorization",
    auth_prefix: "Bearer ",
    note: "OpenAI-compatible /v1 Ollama",
  },
  {
    value: "anthropic-gateway",
    label: "Anthropic-compatible gateway",
    base_url: "https://api.anthropic.com/v1",
    auth_type: "header",
    auth_header: "x-api-key",
    auth_prefix: "",
    note: "Needs an OpenAI-compatible gateway: key goes to x-api-key",
  },
];
