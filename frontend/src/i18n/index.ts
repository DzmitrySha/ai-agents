import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en";
import ru from "./locales/ru";

export type AppLocale = "en" | "ru";

export const LOCALE_STORAGE_KEY = "ai-agents.locale";
export const DEFAULT_LOCALE: AppLocale = "ru";
export const APP_LOCALES: AppLocale[] = ["ru", "en"];

export function readStoredLocale(): AppLocale {
  try {
    const raw = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    if (raw === "en" || raw === "ru") {
      return raw;
    }
  } catch {
    // localStorage unavailable
  }
  return DEFAULT_LOCALE;
}

export function persistLocale(locale: AppLocale): void {
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    // ignore
  }
  document.documentElement.lang = locale;
}

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    ru: { translation: ru },
  },
  lng: typeof window !== "undefined" ? readStoredLocale() : DEFAULT_LOCALE,
  fallbackLng: "en",
  interpolation: { escapeValue: false },
  returnNull: false,
});

if (typeof window !== "undefined") {
  document.documentElement.lang = i18n.language === "en" ? "en" : "ru";
}

i18n.on("languageChanged", (lng) => {
  const locale: AppLocale = lng === "en" ? "en" : "ru";
  persistLocale(locale);
});

export async function setAppLocale(locale: AppLocale): Promise<void> {
  persistLocale(locale);
  await i18n.changeLanguage(locale);
}

export default i18n;
