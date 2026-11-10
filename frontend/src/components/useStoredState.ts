import { useState } from "react";

/** Значение из localStorage (JSON) или fallback, если ключа нет/он битый. */
export function readStored<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function writeStored<T>(key: string, value: T): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // localStorage недоступен — состояние просто не запомнится
  }
}

/**
 * useState с сохранением в localStorage: переключатели и фильтры переживают
 * переход по пунктам меню и перезагрузку страницы.
 */
export function useStoredState<T>(
  key: string,
  fallback: T,
): [T, (value: T | ((prev: T) => T)) => void] {
  const [state, setState] = useState<T>(() => readStored(key, fallback));
  const update = (value: T | ((prev: T) => T)) => {
    setState((prev) => {
      const next = typeof value === "function" ? (value as (prev: T) => T)(prev) : value;
      writeStored(key, next);
      return next;
    });
  };
  return [state, update];
}
