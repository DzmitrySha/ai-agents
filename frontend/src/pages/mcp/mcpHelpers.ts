/** Shared MCP page helpers (server presets, client config snippet). */

export interface ServerForm {
  slug: string;
  name: string;
  description: string;
  agent_slugs: string[];
  tool_slugs: string[];
  skill_slugs: string[];
}

export const EMPTY_SERVER: ServerForm = {
  slug: "",
  name: "",
  description: "",
  agent_slugs: [],
  tool_slugs: [],
  skill_slugs: [],
};

export type ServerPresetId = "cursor" | "claudeDesktop" | "ciBot";

/** Preset ids + slugs; labels/name/description come from i18n `mcp.presets.*`. */
export const SERVER_PRESETS: { id: ServerPresetId; slug: string }[] = [
  { id: "cursor", slug: "cursor" },
  { id: "claudeDesktop", slug: "claude-desktop" },
  { id: "ciBot", slug: "ci-bot" },
];

export function clientConfig(url: string, apiKey: string): string {
  return JSON.stringify(
    { mcpServers: { "ai-agents": { url, headers: { Authorization: `Bearer ${apiKey}` } } } },
    null,
    2,
  );
}

export function mcpEndpoint(): string {
  if (typeof window === "undefined") {
    return "https://ai-agents.example/mcp";
  }
  return `${window.location.origin}/mcp`;
}

export function clientConfigTemplate(url: string): string {
  return clientConfig(url, "mcp-ag-…");
}

export async function copyText(value: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    return false;
  }
}
