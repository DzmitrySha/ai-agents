import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  MantineProvider,
  createTheme,
  type MantineColorScheme,
  type MantineColorsTuple,
} from "@mantine/core";
import { Notifications } from "@mantine/notifications";

export type ThemeMode = "light" | "dark" | "portracker";

const STORAGE_KEY = "ai-agents-theme";
const MODES: ThemeMode[] = ["light", "dark", "portracker"];

/** Portracker-like dark surface: navy body, lighter panels, cool borders. */
const PORTTRACKER_DARK: MantineColorsTuple = [
  "#e8ebf5",
  "#cdd4e4",
  "#9aa4bd",
  "#6c7793",
  "#2b3752",
  "#1d273c",
  "#141c2e",
  "#0d1422",
  "#0a101b",
  "#070b13",
];

/** Indigo accent from the portracker sidebar/port pills. */
const PORTTRACKER_PRIMARY: MantineColorsTuple = [
  "#eef1ff",
  "#d9defe",
  "#b4bdfb",
  "#8f9af8",
  "#6d7bf6",
  "#5a68f4",
  "#4a57da",
  "#3b46b4",
  "#2e378d",
  "#232a6b",
];

export const portrackerTheme = createTheme({
  primaryColor: "portracker",
  primaryShade: { light: 6, dark: 5 },
  colors: {
    portracker: PORTTRACKER_PRIMARY,
    dark: PORTTRACKER_DARK,
  },
  defaultRadius: "md",
  black: "#0a101b",
});

interface ThemeModeContextValue {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
}

const ThemeModeContext = createContext<ThemeModeContextValue>({
  mode: "light",
  setMode: () => undefined,
});

function readStoredMode(): ThemeMode {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored && MODES.includes(stored as ThemeMode)) {
      return stored as ThemeMode;
    }
  } catch {
    // localStorage недоступен — остаёмся на светлой теме
  }
  return "light";
}

export function ThemeRoot({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(readStoredMode);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      // ignore
    }
    document.documentElement.dataset.theme = mode;
  }, [mode]);

  const value = useMemo(() => ({ mode, setMode }), [mode]);
  // light/dark — штатные схемы Mantine; portracker — та же тёмная схема с кастомной палитрой.
  const forceColorScheme: MantineColorScheme = mode === "light" ? "light" : "dark";

  return (
    <ThemeModeContext.Provider value={value}>
      <MantineProvider
        defaultColorScheme="light"
        forceColorScheme={forceColorScheme}
        theme={mode === "portracker" ? portrackerTheme : undefined}
      >
        <Notifications position="top-right" zIndex={4000} />
        {children}
      </MantineProvider>
    </ThemeModeContext.Provider>
  );
}

export function useThemeMode(): ThemeModeContextValue {
  return useContext(ThemeModeContext);
}
