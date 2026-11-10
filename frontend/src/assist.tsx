import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

/** Разделы сервиса, которые ассистент умеет заполнять (совпадает с backend `target`). */
export type AssistTarget =
  | "agent"
  | "tool"
  | "llm"
  | "mcp-connection"
  | "mcp-server"
  | "skill"
  | "user"
  | "service-keys"
  | "general";

export type AssistMode = "form" | "advice" | "review" | "test";

export interface AssistForm {
  target: AssistTarget;
  /** Текущие значения формы — уходят в модель как контекст. */
  current: Record<string, unknown>;
  /** Применить предложенные поля; вернуть текст ошибки или null при успехе. */
  apply: (fields: Record<string, unknown>) => string | null;
  /** Установить фильтр списка на странице (`page_search` из ответа ассистента). */
  applyPageSearch?: (query: string) => string | null;
}

interface AssistContextValue {
  form: AssistForm | null;
  registerForm: (form: AssistForm | null) => void;
  opened: boolean;
  setOpened: (value: boolean) => void;
  /** Prefill textarea when opening the panel (e.g. «Заполнить через AI»). */
  draftMessage: string;
  setDraftMessage: (value: string) => void;
  preferredMode: AssistMode | null;
  setPreferredMode: (value: AssistMode | null) => void;
  openAssist: (opts?: { message?: string; mode?: AssistMode }) => void;
}

const AssistContext = createContext<AssistContextValue | null>(null);

export function AssistProvider({ children }: { children: ReactNode }) {
  const [form, setForm] = useState<AssistForm | null>(null);
  const [opened, setOpened] = useState(false);
  const [draftMessage, setDraftMessage] = useState("");
  const [preferredMode, setPreferredMode] = useState<AssistMode | null>(null);
  const openAssist = useCallback((opts?: { message?: string; mode?: AssistMode }) => {
    if (opts?.message) {
      setDraftMessage(opts.message);
    }
    if (opts?.mode) {
      setPreferredMode(opts.mode);
    }
    setOpened(true);
  }, []);
  const value = useMemo<AssistContextValue>(
    () => ({
      form,
      registerForm: setForm,
      opened,
      setOpened,
      draftMessage,
      setDraftMessage,
      preferredMode,
      setPreferredMode,
      openAssist,
    }),
    [form, opened, draftMessage, preferredMode, openAssist],
  );
  return <AssistContext.Provider value={value}>{children}</AssistContext.Provider>;
}

export function useAssist(): AssistContextValue {
  const value = useContext(AssistContext);
  if (value === null) {
    throw new Error("useAssist must be used inside AssistProvider");
  }
  return value;
}

/**
 * Регистрирует форму страницы для ассистента. `current`/`apply` держим в ref,
 * чтобы не перерегистрировать форму на каждый рендер.
 */
export function useAssistForm(
  target: AssistTarget,
  current: Record<string, unknown>,
  apply: (fields: Record<string, unknown>) => string | null,
  applyPageSearch?: (query: string) => string | null,
): void {
  const { registerForm } = useAssist();
  const currentRef = useRef(current);
  const applyRef = useRef(apply);
  const applyPageSearchRef = useRef(applyPageSearch);
  currentRef.current = current;
  applyRef.current = apply;
  applyPageSearchRef.current = applyPageSearch;

  const stableApply = useCallback(
    (fields: Record<string, unknown>) => applyRef.current(fields),
    [],
  );

  useEffect(() => {
    registerForm({
      target,
      get current() {
        return currentRef.current;
      },
      apply: stableApply,
      get applyPageSearch() {
        return applyPageSearchRef.current ?? undefined;
      },
    });
    return () => registerForm(null);
  }, [registerForm, stableApply, target]);
}
