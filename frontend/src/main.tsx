import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./i18n";
import { App } from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ThemeRoot } from "./theme";
import "@mantine/core/styles.css";
import "@mantine/charts/styles.css";
import "@mantine/notifications/styles.css";
import "./theme.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeRoot>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </ThemeRoot>
  </StrictMode>,
);
