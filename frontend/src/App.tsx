import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate, RouterProvider, createBrowserRouter } from "react-router-dom";
import { Center, Loader } from "@mantine/core";
import { fetchMe } from "./api";
import type { Me } from "./types";
import { AppLayout } from "./components/AppLayout";
import { UnsavedChangesProvider } from "./unsavedChanges";
import { LoginPage } from "./pages/LoginPage";
import { AgentsPage } from "./pages/AgentsPage";
import { AgentEditorPage } from "./pages/AgentEditorPage";
import { RunsPage } from "./pages/RunsPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { RunComparePage } from "./pages/RunComparePage";
import { ToolsPage } from "./pages/ToolsPage";
import { McpPage } from "./pages/McpPage";
import { SkillsPage } from "./pages/SkillsPage";
import { ServiceKeysPage } from "./pages/ServiceKeysPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StatsPage } from "./pages/StatsPage";
import { UsersPage } from "./pages/UsersPage";
import { DoctorPage } from "./pages/DoctorPage";
import { SchedulesPage } from "./pages/SchedulesPage";
import { NotificationsPage } from "./pages/NotificationsPage";
import { PacksPage } from "./pages/PacksPage";
import { AboutPage } from "./pages/AboutPage";
import { DocsPage } from "./pages/DocsPage";
import { PreferencesPage } from "./pages/PreferencesPage";

const AuthState = createContext<Me | null>(null);

function useBootMe(): Me | null {
  return useContext(AuthState);
}

function AuthBoot({ children }: { children: ReactNode }) {
  // undefined — сессия ещё проверяется; повторных запросов не делаем
  const [me, setMe] = useState<Me | null | undefined>(undefined);

  useEffect(() => {
    let alive = true;
    void fetchMe().then((value) => {
      if (alive) {
        setMe(value);
      }
    });
    return () => {
      alive = false;
    };
  }, []);

  if (me === undefined) {
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    );
  }

  return <AuthState.Provider value={me}>{children}</AuthState.Provider>;
}

function LoginRoute() {
  const me = useBootMe();
  if (me) {
    return <Navigate to="/agents" replace />;
  }
  return <LoginPage />;
}

function ProtectedLayout() {
  const me = useBootMe();
  if (!me) {
    return <Navigate to="/login" replace />;
  }
  return (
    <UnsavedChangesProvider>
      <AppLayout me={me} />
    </UnsavedChangesProvider>
  );
}

function CatchAll() {
  const me = useBootMe();
  return <Navigate to={me ? "/agents" : "/login"} replace />;
}

const router = createBrowserRouter([
  { path: "/login", element: <LoginRoute /> },
  {
    element: <ProtectedLayout />,
    children: [
      { index: true, element: <Navigate to="/agents" replace /> },
      { path: "agents", element: <AgentsPage /> },
      { path: "agents/new", element: <AgentEditorPage /> },
      { path: "agents/:ref", element: <AgentEditorPage /> },
      { path: "runs", element: <RunsPage /> },
      { path: "schedules", element: <SchedulesPage /> },
      { path: "runs/compare", element: <RunComparePage /> },
      { path: "runs/:id", element: <RunDetailPage /> },
      { path: "tools", element: <ToolsPage /> },
      { path: "skills", element: <SkillsPage /> },
      { path: "integrations/mcp", element: <McpPage /> },
      { path: "admin/keys", element: <ServiceKeysPage /> },
      { path: "admin/llm", element: <SettingsPage /> },
      { path: "stats", element: <StatsPage /> },
      { path: "admin/users", element: <UsersPage /> },
      { path: "admin/doctor", element: <DoctorPage /> },
      { path: "admin/notifications", element: <NotificationsPage /> },
      { path: "admin/packs", element: <PacksPage /> },
      { path: "settings", element: <PreferencesPage /> },
      { path: "about", element: <AboutPage /> },
      { path: "docs", element: <DocsPage /> },
      { path: "docs/:slug", element: <DocsPage /> },
    ],
  },
  { path: "*", element: <CatchAll /> },
]);

export function App() {
  return (
    <AuthBoot>
      <RouterProvider router={router} />
    </AuthBoot>
  );
}
