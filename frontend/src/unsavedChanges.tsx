import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Button, Group, Modal, Stack, Text } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { useBlocker } from "react-router-dom";

type SaveHandler = () => Promise<void> | void;

interface GuardEntry {
  dirty: boolean;
  onSave?: SaveHandler;
}

interface LeaveRequest {
  proceed: () => void;
  reset?: () => void;
  onSave?: SaveHandler;
}

interface UnsavedChangesApi {
  setEntry: (id: string, entry: GuardEntry | null) => void;
  requestLeave: (proceed: () => void, onSave?: SaveHandler) => void;
}

const UnsavedChangesContext = createContext<UnsavedChangesApi | null>(null);

function snapshot(value: unknown): string {
  return JSON.stringify(value);
}

/** Сравнение текущего значения с базовым снимком (после открытия/загрузки/сохранения). */
export function useBaselineDirty<T>(value: T, active = true): {
  dirty: boolean;
  captureBaseline: (next?: T) => void;
} {
  const baselineRef = useRef(snapshot(value));
  const valueRef = useRef(value);
  valueRef.current = value;
  const [version, setVersion] = useState(0);

  const captureBaseline = useCallback((next?: T) => {
    baselineRef.current = snapshot(next !== undefined ? next : valueRef.current);
    setVersion((prev) => prev + 1);
  }, []);

  const dirty = active && snapshot(value) !== baselineRef.current;
  // version участвует в пересчёте после captureBaseline
  void version;
  return { dirty, captureBaseline };
}

export function UnsavedChangesProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const entriesRef = useRef(new Map<string, GuardEntry>());
  const [rev, setRev] = useState(0);
  const [leave, setLeave] = useState<LeaveRequest | null>(null);
  const [saving, setSaving] = useState(false);

  const dirty = useMemo(() => {
    void rev;
    for (const entry of entriesRef.current.values()) {
      if (entry.dirty) {
        return true;
      }
    }
    return false;
  }, [rev]);

  const setEntry = useCallback((id: string, entry: GuardEntry | null) => {
    if (entry === null) {
      entriesRef.current.delete(id);
    } else {
      entriesRef.current.set(id, entry);
    }
    setRev((prev) => prev + 1);
  }, []);

  const collectSave = useCallback((): SaveHandler | undefined => {
    const handlers: SaveHandler[] = [];
    for (const entry of entriesRef.current.values()) {
      if (entry.dirty && entry.onSave) {
        handlers.push(entry.onSave);
      }
    }
    if (handlers.length === 0) {
      return undefined;
    }
    return async () => {
      for (const handler of handlers) {
        await handler();
      }
    };
  }, []);

  const requestLeave = useCallback(
    (proceed: () => void, onSave?: SaveHandler) => {
      let anyDirty = false;
      for (const entry of entriesRef.current.values()) {
        if (entry.dirty) {
          anyDirty = true;
          break;
        }
      }
      if (!anyDirty) {
        proceed();
        return;
      }
      setLeave({
        proceed,
        onSave: onSave ?? collectSave(),
      });
    },
    [collectSave],
  );

  const blocker = useBlocker(dirty);

  useEffect(() => {
    if (blocker.state !== "blocked") {
      return;
    }
    setLeave({
      proceed: () => {
        blocker.proceed?.();
      },
      reset: () => {
        blocker.reset?.();
      },
      onSave: collectSave(),
    });
  }, [blocker, collectSave]);

  useEffect(() => {
    if (!dirty) {
      return;
    }
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  const closeDialog = useCallback((resetBlocker: boolean) => {
    setLeave((prev) => {
      if (resetBlocker) {
        prev?.reset?.();
      }
      return null;
    });
  }, []);

  const discardAndLeave = useCallback(() => {
    const action = leave;
    setLeave(null);
    action?.proceed();
  }, [leave]);

  const saveAndLeave = useCallback(async () => {
    if (!leave) {
      return;
    }
    setSaving(true);
    try {
      if (leave.onSave) {
        await leave.onSave();
      }
      const action = leave;
      setLeave(null);
      action.proceed();
    } catch {
      // Ошибка сохранения показывается в форме; остаёмся на месте.
    } finally {
      setSaving(false);
    }
  }, [leave]);

  const api = useMemo(() => ({ setEntry, requestLeave }), [setEntry, requestLeave]);

  return (
    <UnsavedChangesContext.Provider value={api}>
      {children}
      <Modal
        opened={leave !== null}
        onClose={() => closeDialog(true)}
        title={t("common.unsavedLeave.title")}
        size="sm"
        centered
        closeOnClickOutside={!saving}
        closeOnEscape={!saving}
      >
        <Stack gap="md">
          <Text size="sm">{t("common.unsavedLeave.body")}</Text>
          <Group justify="flex-end" gap="xs">
            <Button variant="default" onClick={() => closeDialog(true)} disabled={saving}>
              {t("common.cancel")}
            </Button>
            <Button variant="default" color="red" onClick={discardAndLeave} disabled={saving}>
              {t("common.unsavedLeave.discard")}
            </Button>
            {leave?.onSave ? (
              <Button onClick={() => void saveAndLeave()} loading={saving}>
                {t("common.unsavedLeave.confirm")}
              </Button>
            ) : null}
          </Group>
        </Stack>
      </Modal>
    </UnsavedChangesContext.Provider>
  );
}

/**
 * Регистрирует «грязную» форму: блокирует навигацию/закрытие вкладки
 * и даёт requestLeave для Modal/Drawer/кнопок «Отмена».
 */
export function useUnsavedGuard(
  id: string,
  dirty: boolean,
  onSave?: SaveHandler,
): { requestLeave: (proceed: () => void) => void } {
  const ctx = useContext(UnsavedChangesContext);
  if (!ctx) {
    throw new Error("useUnsavedGuard requires UnsavedChangesProvider");
  }

  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;
  const hasSave = typeof onSave === "function";

  const stableSave = useMemo(() => {
    if (!hasSave) {
      return undefined;
    }
    return () => onSaveRef.current?.();
  }, [hasSave]);

  useEffect(() => {
    ctx.setEntry(id, { dirty, onSave: stableSave });
    return () => ctx.setEntry(id, null);
  }, [ctx, id, dirty, stableSave]);

  const requestLeave = useCallback(
    (proceed: () => void) => ctx.requestLeave(proceed, stableSave),
    [ctx, stableSave],
  );

  return { requestLeave };
}
