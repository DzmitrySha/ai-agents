import type { Tool, ToolMethod, ToolParamType } from "../../types";

export type NumberField = number | string;

export interface ParamDraft {
  name: string;
  type: ToolParamType;
  description: string;
  required: boolean;
  enum: string;
}

export interface ToolFormState {
  slug: string;
  name: string;
  description: string;
  method: ToolMethod;
  headers: string;
  url: string;
  query: string;
  body_template: string;
  content_type: string;
  timeout_seconds: NumberField;
  enabled: boolean;
  parameters: ParamDraft[];
}

export const METHOD_OPTIONS: { value: ToolMethod; label: string }[] = [
  { value: "GET", label: "GET" },
  { value: "POST", label: "POST" },
  { value: "PUT", label: "PUT" },
  { value: "PATCH", label: "PATCH" },
  { value: "DELETE", label: "DELETE" },
];

export const PARAM_TYPE_OPTIONS: { value: ToolParamType; label: string }[] = [
  { value: "string", label: "string" },
  { value: "number", label: "number" },
  { value: "integer", label: "integer" },
  { value: "boolean", label: "boolean" },
];

export const CONTENT_TYPES = [
  "application/json",
  "application/x-www-form-urlencoded",
  "text/plain",
];

export const EMPTY_TOOL_FORM: ToolFormState = {
  slug: "",
  name: "",
  description: "",
  method: "GET",
  url: "",
  headers: "",
  query: "",
  body_template: "",
  content_type: "application/json",
  timeout_seconds: 20,
  enabled: true,
  parameters: [],
};

export function parseKeyValueLines(text: string): Record<string, string> {
  const result: Record<string, string> = {};
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }
    const index = trimmed.indexOf(":");
    if (index <= 0) {
      continue;
    }
    const key = trimmed.slice(0, index).trim();
    if (key) {
      result[key] = trimmed.slice(index + 1).trim();
    }
  }
  return result;
}

export function parseEnumText(text: string): string[] | null {
  const values = text
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  return values.length ? values : null;
}

export function formFromTool(tool: Tool): ToolFormState {
  return {
    slug: tool.slug,
    name: tool.name,
    description: tool.description ?? "",
    method: tool.method,
    url: tool.url,
    // Secrets not returned by API — leave blank to keep stored headers on PATCH.
    headers: "",
    query: Object.entries(tool.query ?? {})
      .map(([key, value]) => `${key}: ${value}`)
      .join("\n"),
    body_template: tool.body_template ?? "",
    content_type: tool.content_type || "application/json",
    timeout_seconds: tool.timeout_seconds ?? 20,
    enabled: tool.enabled,
    parameters: (tool.parameters ?? []).map((param) => ({
      name: param.name,
      type: param.type,
      description: param.description ?? "",
      required: param.required,
      enum: (param.enum ?? []).join(", "),
    })),
  };
}

export function paramsCount(schema: Record<string, unknown> | undefined): number {
  const properties = (schema as { properties?: Record<string, unknown> } | undefined)?.properties;
  return properties ? Object.keys(properties).length : 0;
}
