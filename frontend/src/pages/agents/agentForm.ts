import type { Agent, AgentKind } from "../../types";

export type NumberField = number | string;

export interface AgentFormState {
  name: string;
  slug: string;
  description: string;
  system_prompt: string;
  kind: AgentKind;
  plugin_name: string;
  tools: string[];
  skills: string[];
  sub_agents: string[];
  memory_enabled: boolean;
  base_url: string;
  model: string;
  temperature: NumberField;
  max_steps: NumberField;
  timeout_seconds: NumberField;
  max_tokens: NumberField;
  max_attempts: NumberField;
  approval_mode: string;
}

export const EMPTY_AGENT_FORM: AgentFormState = {
  name: "",
  slug: "",
  description: "",
  system_prompt: "",
  kind: "preset",
  plugin_name: "",
  tools: [],
  skills: [],
  sub_agents: [],
  memory_enabled: false,
  base_url: "",
  model: "",
  temperature: 0.2,
  max_steps: 8,
  timeout_seconds: 120,
  max_tokens: "",
  max_attempts: "",
  approval_mode: "mutating",
};

export function toNumber(value: NumberField): number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formFromAgent(agent: Agent): AgentFormState {
  return {
    name: agent.name,
    slug: agent.slug,
    description: agent.description ?? "",
    system_prompt: agent.system_prompt ?? "",
    kind: agent.kind,
    plugin_name: agent.plugin_name ?? "",
    tools: agent.tools ?? [],
    skills: agent.skills ?? [],
    sub_agents: agent.sub_agents ?? [],
    memory_enabled: Boolean(agent.memory_enabled),
    base_url: agent.llm?.base_url ?? "",
    model: agent.llm?.model ?? "",
    temperature: agent.llm?.temperature ?? 0.2,
    max_steps: agent.limits?.max_steps ?? 8,
    timeout_seconds: agent.limits?.timeout_seconds ?? 120,
    max_tokens: agent.limits?.max_tokens ?? "",
    max_attempts: agent.limits?.max_attempts ?? "",
    approval_mode: agent.limits?.approval_mode ?? "mutating",
  };
}

/** Ключ sessionStorage: черновик fields с списка агентов → /agents/new. */
export const ASSIST_AGENT_FIELDS_KEY = "ai-agents.assist.agent-fields";

/** Слить ответ ассистента в partial формы (только известные tools/skills). */
export function mergeAssistAgentFields(
  fields: Record<string, unknown>,
  opts: {
    allowSlug: boolean;
    knownTools: Set<string>;
    knownSkills: Set<string>;
  },
): Partial<AgentFormState> {
  const next: Partial<AgentFormState> = {};
  const str = (key: keyof AgentFormState) => {
    const value = fields[key as string];
    if (typeof value === "string" && value.trim()) {
      (next[key] as unknown) = value;
    }
  };
  str("name");
  str("description");
  str("system_prompt");
  if (opts.allowSlug) {
    str("slug");
  }
  if (Array.isArray(fields.tools)) {
    const filtered = fields.tools
      .map((item) => String(item))
      .filter((item) => opts.knownTools.has(item));
    if (filtered.length) {
      next.tools = filtered;
    }
  }
  if (Array.isArray(fields.skills)) {
    const filtered = fields.skills
      .map((item) => String(item))
      .filter((item) => opts.knownSkills.has(item));
    if (filtered.length) {
      next.skills = filtered;
    }
  }
  const limits = fields.limits;
  if (limits && typeof limits === "object" && !Array.isArray(limits)) {
    const source = limits as Record<string, unknown>;
    const steps = Number(source.max_steps);
    if (Number.isFinite(steps) && steps >= 1) {
      next.max_steps = Math.min(100, Math.round(steps));
    }
    const timeout = Number(source.timeout_seconds);
    if (Number.isFinite(timeout) && timeout >= 1) {
      next.timeout_seconds = Math.min(3600, Math.round(timeout));
    }
  }
  const llm = fields.llm;
  if (llm && typeof llm === "object" && !Array.isArray(llm)) {
    const source = llm as Record<string, unknown>;
    if (typeof source.base_url === "string") {
      next.base_url = source.base_url;
    }
    if (typeof source.model === "string") {
      next.model = source.model;
    }
    const temperature = Number(source.temperature);
    if (Number.isFinite(temperature)) {
      next.temperature = Math.min(1, Math.max(0, temperature));
    }
  }
  return next;
}
