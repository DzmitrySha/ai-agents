import i18n from "./i18n";

export function formatDate(value: string | null | undefined): string {
  if (!value) {
    return i18n.t("common.emptyDash");
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  const locale = i18n.language?.startsWith("en") ? "en-GB" : "ru-RU";
  return date.toLocaleString(locale, { dateStyle: "short", timeStyle: "short" });
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined) {
    return i18n.t("common.emptyDash");
  }
  if (typeof value === "string") {
    return value;
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
