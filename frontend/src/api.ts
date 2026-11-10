import i18n from "./i18n";
import type { Me } from "./types";

export const UI_REQUEST_HEADER = "ai-agents-ui";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function loginRedirect(): void {
  const target = window.location.pathname + window.location.search;
  window.location.assign(`/auth/login?return_to=${encodeURIComponent(target)}`);
}

function detailMessage(parsed: unknown): string | null {
  if (parsed === null || typeof parsed !== "object") {
    return null;
  }
  if ("detail" in parsed) {
    if (typeof parsed.detail === "string") {
      return parsed.detail;
    }
    if (parsed.detail !== undefined) {
      return JSON.stringify(parsed.detail);
    }
  }
  if ("message" in parsed && typeof parsed.message === "string") {
    return parsed.message;
  }
  return null;
}

async function readError(res: Response): Promise<string> {
  const text = await res.text().catch(() => "");
  if (!text) {
    return `HTTP ${res.status}`;
  }
  try {
    const message = detailMessage(JSON.parse(text));
    if (message !== null) {
      return message;
    }
  } catch {
    // тело не JSON — отдаём как есть
  }
  return text;
}

/**
 * Запрос к API: cookie-сессия, CSRF-заголовок UI, JSON-тело, авто-редирект на логин при 401.
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Requested-With", UI_REQUEST_HEADER);
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(path, { ...init, headers, credentials: "include" });

  if (res.status === 401) {
    loginRedirect();
    throw new ApiError(401, i18n.t("common.authRequired"));
  }
  if (!res.ok) {
    throw new ApiError(res.status, await readError(res));
  }
  if (res.status === 204) {
    return undefined as T;
  }

  const text = await res.text();
  if (!text) {
    return undefined as T;
  }
  return JSON.parse(text) as T;
}

/** Текущая сессия без авто-редиректа: null, если пользователь не авторизован. */
export async function fetchMe(): Promise<Me | null> {
  try {
    const res = await fetch("/auth/me", {
      credentials: "include",
      headers: { "X-Requested-With": UI_REQUEST_HEADER },
    });
    if (res.status === 401) {
      return null;
    }
    if (!res.ok) {
      return null;
    }
    const me = (await res.json()) as Me;
    return me.authenticated ? me : null;
  } catch {
    return null;
  }
}

export async function logout(): Promise<void> {
  await apiFetch<void>("/auth/logout", { method: "POST" });
}

export function jsonBody(value: unknown): BodyInit {
  return JSON.stringify(value);
}

export function buildQuery(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") {
      continue;
    }
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

/** Терпимо к `T[]` и `{"items": T[]}` — контракт списков в разных роутах отличается. */
export function asItems<T>(data: T[] | { items?: T[] } | null | undefined): T[] {
  if (Array.isArray(data)) {
    return data;
  }
  if (data && Array.isArray(data.items)) {
    return data.items;
  }
  return [];
}

/** Человеческий текст ошибки для алертов (ApiError → detail, иначе message). */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    return err.message;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return String(err);
}
