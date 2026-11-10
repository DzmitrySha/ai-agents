import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Code,
  Group,
  Loader,
  NumberInput,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Tabs,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { apiFetch, asItems, buildQuery, jsonBody } from "../api";
import { NO_AUTOFILL } from "../formAttrs";
import { useAssist, useAssistForm } from "../assist";
import { useSession } from "../components/AppLayout";
import { notifySuccess } from "../notify";
import {
  IconAction,
  PageHeader,
  PageSearch,
  readViewMode,
  saveViewMode,
  ViewToggle,
  type ViewMode,
} from "../components/PageHeader";
import { PlusIcon } from "../components/icons";
import { formatDate } from "../format";
import type {
  Agent,
  AgentList,
  McpConnection,
  McpConnectionDeleteResult,
  McpConnectionTestResult,
  McpServer,
  McpServerCreated,
  SkillList,
  ToolSpec,
} from "../types";
import { AllowlistMultiSelect } from "../components/AllowlistMultiSelect";
import {
  EMPTY_SERVER,
  SERVER_PRESETS,
  clientConfig,
  clientConfigTemplate,
  copyText,
  mcpEndpoint,
  type ServerForm,
} from "./mcp/mcpHelpers";
import { useBaselineDirty, useUnsavedGuard } from "../unsavedChanges";
import { matchesPageSearch } from "../pageSearch";

interface ConnectionForm {
  slug: string;
  name: string;
  description: string;
  url: string;
  timeout_seconds: number;
  enabled: boolean;
  headers: string;
}

const EMPTY_CONNECTION: ConnectionForm = {
  slug: "",
  name: "",
  description: "",
  url: "",
  timeout_seconds: 30,
  enabled: true,
  headers: "",
};

function ServerActions({
  server,
  busy,
  openEditServer,
  toggleServer,
  deleteServer,
}: {
  server: McpServer;
  busy: string | null;
  openEditServer: (server: McpServer) => void;
  toggleServer: (server: McpServer) => unknown;
  deleteServer: (server: McpServer) => unknown;
}) {
  const { t } = useTranslation();
  return (
    <Group gap={6} justify="flex-end" wrap="nowrap">
      <IconAction
        kind="edit"
        label={t("common.edit")}
        onClick={() => openEditServer(server)}
      />
      <IconAction
        kind="toggle"
        label={server.enabled ? t("mcp.disable") : t("mcp.enable")}
        loading={busy === `server-toggle-${server.id}`}
        onClick={() => void toggleServer(server)}
      />
      <IconAction
        kind="delete"
        label={t("common.delete")}
        loading={busy === `server-delete-${server.id}`}
        onClick={() => void deleteServer(server)}
      />
    </Group>
  );
}

function ConnectionActions({
  connection,
  busy,
  canWrite,
  testConnection,
  openEditConnection,
  deleteConnection,
}: {
  connection: McpConnection;
  busy: string | null;
  canWrite: boolean;
  testConnection: (connection: McpConnection) => unknown;
  openEditConnection: (connection: McpConnection) => void;
  deleteConnection: (connection: McpConnection) => unknown;
}) {
  const { t } = useTranslation();
  return (
    <Group gap={6} justify="flex-end" wrap="nowrap">
      <IconAction
        kind="test"
        label={t("mcp.check")}
        loading={busy === `connection-test-${connection.id}`}
        onClick={() => void testConnection(connection)}
      />
      <IconAction
        kind="edit"
        label={t("common.edit")}
        disabled={!canWrite}
        onClick={() => openEditConnection(connection)}
      />
      <IconAction
        kind="delete"
        label={t("common.delete")}
        disabled={!canWrite}
        loading={busy === `connection-delete-${connection.id}`}
        onClick={() => void deleteConnection(connection)}
      />
    </Group>
  );
}

export function McpPage() {
  const { t } = useTranslation();
  const me = useSession();
  const { openAssist } = useAssist();
  const isSuperadmin = me.user.is_superadmin;
  const canWrite = isSuperadmin || (me.user.app_role ?? "user") !== "user";

  const [tab, setTab] = useState<string | null>(isSuperadmin ? "servers" : "connections");
  const [view, setView] = useState<ViewMode>(() => readViewMode("mcp"));
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [servers, setServers] = useState<McpServer[]>([]);
  const [serversLoading, setServersLoading] = useState(true);
  const [sharedAgents, setSharedAgents] = useState<Agent[]>([]);
  const [toolOptions, setToolOptions] = useState<{ value: string; label: string }[]>([]);
  const [skillOptions, setSkillOptions] = useState<{ value: string; label: string }[]>([]);
  const [serverForm, setServerForm] = useState<ServerForm>(EMPTY_SERVER);
  const [serverModal, setServerModal] = useState<{ editing: string | null } | null>(null);
  const [issued, setIssued] = useState<{ url: string; apiKey: string } | null>(null);
  const { dirty: serverDirty, captureBaseline: captureServer } = useBaselineDirty(
    serverForm,
    serverModal !== null,
  );

  const [connections, setConnections] = useState<McpConnection[]>([]);
  const [connectionsLoading, setConnectionsLoading] = useState(true);
  const [connectionForm, setConnectionForm] = useState<ConnectionForm>(EMPTY_CONNECTION);
  const [connectionModal, setConnectionModal] = useState<{ editing: string | null } | null>(null);
  const { dirty: connectionDirty, captureBaseline: captureConnection } = useBaselineDirty(
    connectionForm,
    connectionModal !== null,
  );
  const [formError, setFormError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<
    { slug: string; result: McpConnectionTestResult } | null
  >(null);

  const [busy, setBusy] = useState<string | null>(null);
  const [pageSearch, setPageSearch] = useState("");

  const filteredServers = useMemo(() => {
    if (!pageSearch.trim()) {
      return servers;
    }
    return servers.filter((server) =>
      matchesPageSearch(pageSearch, [
        server.name,
        server.slug,
        server.description,
        ...(server.agent_slugs ?? []),
        ...(server.tool_slugs ?? []),
        ...(server.skill_slugs ?? []),
      ]),
    );
  }, [servers, pageSearch]);

  const filteredConnections = useMemo(() => {
    if (!pageSearch.trim()) {
      return connections;
    }
    return connections.filter((connection) =>
      matchesPageSearch(pageSearch, [
        connection.name,
        connection.slug,
        connection.url,
        connection.description,
        ...connection.header_names,
      ]),
    );
  }, [connections, pageSearch]);

  useAssistForm(
    tab === "servers" ? "mcp-server" : "mcp-connection",
    tab === "servers"
      ? serverModal !== null
        ? {
            page_search: pageSearch,
            slug: serverForm.slug,
            name: serverForm.name,
            description: serverForm.description,
            agent_slugs: serverForm.agent_slugs,
            tool_slugs: serverForm.tool_slugs,
            skill_slugs: serverForm.skill_slugs,
            endpoint: mcpEndpoint(),
            taken_slugs: servers.map((server) => server.slug),
            published_agents: sharedAgents.map((agent) => agent.slug),
            hint: t("mcp.assistHintServers"),
          }
        : {
            page_search: pageSearch,
            taken_slugs: servers.map((server) => server.slug),
            published_agents: sharedAgents.map((agent) => agent.slug),
            endpoint: mcpEndpoint(),
            hint: t("mcp.assistHintServers"),
          }
      : connectionModal !== null
        ? {
            page_search: pageSearch,
            slug: connectionForm.slug,
            name: connectionForm.name,
            description: connectionForm.description,
            url: connectionForm.url,
            headers: connectionForm.headers,
            timeout_seconds: connectionForm.timeout_seconds,
            enabled: connectionForm.enabled,
            taken_slugs: connections.map((connection) => connection.slug),
            hint: t("mcp.assistHintConnections"),
          }
        : {
            page_search: pageSearch,
            taken_slugs: connections.map((connection) => connection.slug),
            hint: t("mcp.assistHintConnections"),
          },
    (fields) => {
      const { page_search: _ps, ...rest } = fields;
      if (tab === "servers") {
        const next = { ...serverForm };
        let touched = false;
        for (const key of ["slug", "name", "description"] as const) {
          const value = rest[key];
          if (typeof value === "string" && (value.trim() || key === "description")) {
            next[key] = value;
            touched = true;
          }
        }
        for (const key of ["agent_slugs", "tool_slugs", "skill_slugs"] as const) {
          const value = rest[key];
          if (Array.isArray(value)) {
            next[key] = value.map(String).filter(Boolean);
            touched = true;
          }
        }
        if (!touched) {
          return Object.keys(rest).length === 0 ? null : t("mcp.noServerFields");
        }
        if (serverModal === null) {
          captureServer(EMPTY_SERVER);
        }
        setServerForm(next);
        setServerModal({ editing: null });
        return null;
      }
      const next = { ...connectionForm };
      let touched = false;
      for (const key of ["slug", "name", "description", "url"] as const) {
        const value = rest[key];
        if (typeof value === "string" && (value.trim() || key === "description")) {
          next[key] = value;
          touched = true;
        }
      }
      if (rest.headers && typeof rest.headers === "object" && !Array.isArray(rest.headers)) {
        next.headers = JSON.stringify(rest.headers, null, 2);
        touched = true;
      }
      const timeout = Number(rest.timeout_seconds);
      if (Number.isFinite(timeout) && timeout >= 1) {
        next.timeout_seconds = Math.min(120, Math.round(timeout));
        touched = true;
      }
      if (typeof rest.enabled === "boolean") {
        next.enabled = rest.enabled;
        touched = true;
      }
      if (!touched) {
        return Object.keys(rest).length === 0 ? null : t("mcp.noConnectionFields");
      }
      if (connectionModal === null) {
        captureConnection(EMPTY_CONNECTION);
      }
      setConnectionForm(next);
      setConnectionModal({ editing: null });
      return null;
    },
    (query) => {
      setPageSearch(query);
      return null;
    },
  );

  const loadServers = useCallback(async () => {
    if (!isSuperadmin) {
      setServersLoading(false);
      return;
    }
    try {
      const data = await apiFetch<{ items: McpServer[] } | McpServer[]>(
        "/api/admin/mcp-servers",
      );
      setServers(asItems(data));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setServers([]);
    } finally {
      setServersLoading(false);
    }
  }, [isSuperadmin]);

  const loadSharedAgents = useCallback(async () => {
    if (!isSuperadmin) return;
    try {
      const data = await apiFetch<AgentList>(
        `/v1/agents${buildQuery({ scope: "shared", limit: 200 })}`,
      );
      setSharedAgents(
        (data.items ?? []).filter(
          (agent) => agent.status === "published" && agent.visibility === "shared",
        ),
      );
    } catch {
      setSharedAgents([]);
    }
  }, [isSuperadmin]);

  const loadCatalogOptions = useCallback(async () => {
    if (!isSuperadmin) return;
    try {
      const [tools, skills] = await Promise.all([
        apiFetch<ToolSpec[]>("/v1/tools"),
        apiFetch<SkillList>("/v1/skills"),
      ]);
      setToolOptions(
        (tools ?? []).map((tool) => ({
          value: tool.name,
          label: `${tool.name}${tool.source ? ` (${tool.source})` : ""}`,
        })),
      );
      setSkillOptions(
        (skills.items ?? []).map((skill) => ({
          value: skill.slug,
          label: `${skill.name} (${skill.slug})`,
        })),
      );
    } catch {
      setToolOptions([]);
      setSkillOptions([]);
    }
  }, [isSuperadmin]);

  const loadConnections = useCallback(async () => {
    try {
      const data = await apiFetch<{ items: McpConnection[] } | McpConnection[]>(
        "/v1/mcp-connections",
      );
      setConnections(asItems(data));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setConnections([]);
    } finally {
      setConnectionsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadServers();
  }, [loadServers]);

  useEffect(() => {
    void loadSharedAgents();
  }, [loadSharedAgents]);

  useEffect(() => {
    void loadCatalogOptions();
  }, [loadCatalogOptions]);

  useEffect(() => {
    void loadConnections();
  }, [loadConnections]);

  const agentOptions = sharedAgents.map((agent) => ({
    value: agent.slug,
    label: `${agent.name} (${agent.slug})`,
  }));

  const run = async (key: string, action: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    setNotice(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const persistServer = async () => {
    const editing = serverModal?.editing ?? null;
    const payload = {
      name: serverForm.name.trim(),
      description: serverForm.description.trim(),
      agent_slugs: serverForm.agent_slugs,
      tool_slugs: serverForm.tool_slugs,
      skill_slugs: serverForm.skill_slugs,
    };
    if (editing) {
      await apiFetch<McpServer>(`/api/admin/mcp-servers/${encodeURIComponent(editing)}`, {
        method: "PATCH",
        body: jsonBody(payload),
      });
      captureServer(serverForm);
      notifySuccess(t("mcp.serverUpdated", { name: payload.name }));
    } else {
      const created = await apiFetch<McpServerCreated>("/api/admin/mcp-servers", {
        method: "POST",
        body: jsonBody({
          slug: serverForm.slug.trim(),
          ...payload,
        }),
      });
      const next: ServerForm = {
        slug: created.slug,
        name: created.name,
        description: created.description,
        agent_slugs: [...(created.agent_slugs ?? [])],
        tool_slugs: [...(created.tool_slugs ?? [])],
        skill_slugs: [...(created.skill_slugs ?? [])],
      };
      setIssued({ url: created.url, apiKey: created.api_key });
      setServerForm(next);
      captureServer(next);
      setServerModal({ editing: created.slug });
      notifySuccess(t("mcp.serverCreated", { name: created.name }));
    }
    await loadServers();
  };

  const createServer = () => run(serverModal?.editing ? "server-save" : "server-create", persistServer);

  const openServerModal = () => {
    setIssued(null);
    setServerForm(EMPTY_SERVER);
    captureServer(EMPTY_SERVER);
    setServerModal({ editing: null });
  };

  const openEditServer = (server: McpServer) => {
    const next: ServerForm = {
      slug: server.slug,
      name: server.name,
      description: server.description,
      agent_slugs: [...(server.agent_slugs ?? [])],
      tool_slugs: [...(server.tool_slugs ?? [])],
      skill_slugs: [...(server.skill_slugs ?? [])],
    };
    setIssued(null);
    setServerForm(next);
    captureServer(next);
    setServerModal({ editing: server.slug });
  };

  const closeServerModal = () => setServerModal(null);

  const rotateServerKey = () => {
    const slug = serverModal?.editing;
    if (!slug) return;
    void run("server-rotate", async () => {
      const rotated = await apiFetch<McpServerCreated>(
        `/api/admin/mcp-servers/${encodeURIComponent(slug)}`,
        { method: "PATCH", body: jsonBody({ rotate_key: true }) },
      );
      setIssued({ url: rotated.url, apiKey: rotated.api_key });
      notifySuccess(t("mcp.keyRotated"));
      await loadServers();
    });
  };

  const toggleServer = (server: McpServer) =>
    run(`server-toggle-${server.id}`, async () => {
      await apiFetch<McpServer>(`/api/admin/mcp-servers/${encodeURIComponent(server.slug)}`, {
        method: "PATCH",
        body: jsonBody({ enabled: !server.enabled }),
      });
      await loadServers();
    });

  const deleteServer = (server: McpServer) =>
    run(`server-delete-${server.id}`, async () => {
      await apiFetch<void>(`/api/admin/mcp-servers/${encodeURIComponent(server.slug)}`, {
        method: "DELETE",
      });
      setNotice(t("mcp.serverDeleted", { name: server.name }));
      await loadServers();
    });

  const openCreateConnection = () => {
    setConnectionForm(EMPTY_CONNECTION);
    captureConnection(EMPTY_CONNECTION);
    setFormError(null);
    setConnectionModal({ editing: null });
  };

  const openEditConnection = (connection: McpConnection) => {
    const next = {
      slug: connection.slug,
      name: connection.name,
      description: connection.description,
      url: connection.url,
      timeout_seconds: connection.timeout_seconds,
      enabled: connection.enabled,
      headers: "",
    };
    setConnectionForm(next);
    captureConnection(next);
    setFormError(null);
    setConnectionModal({ editing: connection.slug });
  };

  const closeConnectionModal = () => setConnectionModal(null);

  const persistConnection = async () => {
    const editing = connectionModal?.editing ?? null;
    let headers: Record<string, string> | null = null;
    const rawHeaders = connectionForm.headers.trim();
    if (rawHeaders) {
      try {
        const parsed: unknown = JSON.parse(rawHeaders);
        if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
          throw new Error("headers must be a JSON object");
        }
        headers = Object.fromEntries(
          Object.entries(parsed as Record<string, unknown>).map(([key, value]) => [
            key,
            String(value),
          ]),
        );
      } catch (err) {
        throw new Error(
          t("mcp.headersError", {
            message: err instanceof Error ? err.message : String(err),
          }),
        );
      }
    }

    const body: Record<string, unknown> = {
      name: connectionForm.name.trim(),
      description: connectionForm.description.trim(),
      url: connectionForm.url.trim(),
      timeout_seconds: connectionForm.timeout_seconds,
      enabled: connectionForm.enabled,
    };
    if (headers !== null) {
      body.headers = headers;
    }
    if (editing) {
      await apiFetch<McpConnection>(`/v1/mcp-connections/${encodeURIComponent(editing)}`, {
        method: "PATCH",
        body: jsonBody(body),
      });
    } else {
      body.slug = connectionForm.slug.trim();
      await apiFetch<McpConnection>("/v1/mcp-connections", {
        method: "POST",
        body: jsonBody(body),
      });
    }
    captureConnection(connectionForm);
    setConnectionModal(null);
    const msg = editing ? t("mcp.connectionSaved") : t("mcp.connectionCreated");
    setNotice(msg);
    notifySuccess(msg);
    await loadConnections();
  };

  const saveConnection = () =>
    run("connection-save", async () => {
      try {
        await persistConnection();
      } catch (err) {
        setFormError(err instanceof Error ? err.message : String(err));
        throw err;
      }
    });

  const { requestLeave: requestServerLeave } = useUnsavedGuard(
    "mcp-server-modal",
    serverModal !== null && serverDirty,
    async () => {
      try {
        await persistServer();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        throw err;
      }
    },
  );

  const { requestLeave: requestConnectionLeave } = useUnsavedGuard(
    "mcp-connection-modal",
    connectionModal !== null && connectionDirty,
    async () => {
      setFormError(null);
      try {
        await persistConnection();
      } catch (err) {
        setFormError(err instanceof Error ? err.message : String(err));
        throw err;
      }
    },
  );

  const testConnection = (connection: McpConnection) =>
    run(`connection-test-${connection.id}`, async () => {
      const result = await apiFetch<McpConnectionTestResult>(
        `/v1/mcp-connections/${encodeURIComponent(connection.slug)}/test`,
        { method: "POST" },
      );
      setTestResult({ slug: connection.slug, result });
      await loadConnections();
    });

  const deleteConnection = (connection: McpConnection) =>
    run(`connection-delete-${connection.id}`, async () => {
      const result = await apiFetch<McpConnectionDeleteResult>(
        `/v1/mcp-connections/${encodeURIComponent(connection.slug)}`,
        { method: "DELETE" },
      );
      setNotice(
        result.detached_agents.length
          ? t("mcp.connectionDeletedDetached", {
              agents: result.detached_agents.join(", "),
            })
          : t("mcp.connectionDeleted"),
      );
      await loadConnections();
    });

  if (serverModal !== null) {
    const editing = serverModal.editing;
    return (
      <Stack gap="md">
        <Group justify="space-between" align="center">
          <Title order={2}>
            {editing ? t("mcp.editServer") : t("mcp.newServer")}
          </Title>
          <Button variant="default" onClick={() => requestServerLeave(closeServerModal)}>
            {t("common.backToList")}
          </Button>
        </Group>
        <Stack gap="sm" maw={640}>
          <Text size="sm" c="dimmed">
            {editing ? t("mcp.serverHintEdit") : t("mcp.serverHintCreate")}
          </Text>
          {editing ? null : (
            <Group gap="xs">
              {SERVER_PRESETS.map((preset) => (
                <Button
                  key={preset.id}
                  size="xs"
                  variant="light"
                  onClick={() =>
                    setServerForm({
                      slug: preset.slug,
                      name: t(`mcp.presets.${preset.id}.name`),
                      description: t(`mcp.presets.${preset.id}.description`),
                      agent_slugs: serverForm.agent_slugs,
                      tool_slugs: serverForm.tool_slugs,
                      skill_slugs: serverForm.skill_slugs,
                    })
                  }
                >
                  {t(`mcp.presets.${preset.id}.label`)}
                </Button>
              ))}
              <Button
                size="xs"
                variant="subtle"
                onClick={() =>
                  openAssist({
                    mode: "form",
                    message: t("mcp.assistServerHint"),
                  })
                }
              >
                {t("mcp.fillViaAi")}
              </Button>
            </Group>
          )}
          <TextInput
            {...NO_AUTOFILL}
            label={t("common.slug")}
            placeholder="cursor"
            value={serverForm.slug}
            onChange={(event) =>
              setServerForm({ ...serverForm, slug: event.currentTarget.value })
            }
            disabled={Boolean(editing)}
            required
          />
          <TextInput
            {...NO_AUTOFILL}
            label={t("common.name")}
            placeholder={t("mcp.namePlaceholderServer")}
            value={serverForm.name}
            onChange={(event) =>
              setServerForm({ ...serverForm, name: event.currentTarget.value })
            }
            required
          />
          <TextInput
            {...NO_AUTOFILL}
            label={t("common.description")}
            value={serverForm.description}
            onChange={(event) =>
              setServerForm({ ...serverForm, description: event.currentTarget.value })
            }
          />
          <AllowlistMultiSelect
            label={t("mcp.agentsAllowlist")}
            description={t("mcp.agentsAllowlistHint")}
            data={agentOptions}
            value={serverForm.agent_slugs}
            onChange={(value) => setServerForm({ ...serverForm, agent_slugs: value })}
            nothingFoundMessage={t("mcp.noPublishedShared")}
          />
          <AllowlistMultiSelect
            label={t("mcp.toolsAllowlist")}
            description={t("mcp.toolsAllowlistHint")}
            data={toolOptions}
            value={serverForm.tool_slugs}
            onChange={(value) => setServerForm({ ...serverForm, tool_slugs: value })}
            nothingFoundMessage={t("mcp.noTools")}
          />
          <AllowlistMultiSelect
            label={t("mcp.skillsAllowlist")}
            description={t("mcp.skillsAllowlistHint")}
            data={skillOptions}
            value={serverForm.skill_slugs}
            onChange={(value) => setServerForm({ ...serverForm, skill_slugs: value })}
            nothingFoundMessage={t("mcp.noSkills")}
          />
          <Stack gap="xs">
            <Group justify="space-between" align="center" wrap="nowrap">
              <Text size="xs" fw={600}>
                {editing ? t("mcp.clientConfigTitle") : t("mcp.configPreviewTitle")}
              </Text>
              {editing ? (
                <Button
                  size="xs"
                  variant="light"
                  loading={busy === "server-rotate"}
                  onClick={rotateServerKey}
                >
                  {t("mcp.newKey")}
                </Button>
              ) : null}
            </Group>
            {issued ? (
              <Alert color="green" variant="light">
                {t("mcp.keyOnce")}
              </Alert>
            ) : editing ? (
              <Text size="xs" c="dimmed">
                {t("mcp.keyNotShown")}
              </Text>
            ) : null}
            <Code block style={{ fontSize: 11, whiteSpace: "pre-wrap" }}>
              {issued
                ? clientConfig(issued.url, issued.apiKey)
                : clientConfigTemplate(mcpEndpoint())}
            </Code>
            {issued ? (
              <Group>
                <Button
                  size="xs"
                  variant="default"
                  onClick={() => void copyText(clientConfig(issued.url, issued.apiKey))}
                >
                  {t("mcp.copyConfig")}
                </Button>
                <Button size="xs" variant="subtle" onClick={() => setIssued(null)}>
                  {t("common.hide")}
                </Button>
              </Group>
            ) : null}
          </Stack>
          <Group>
            <Button
              onClick={() => void createServer()}
              loading={busy === "server-create" || busy === "server-save"}
              disabled={!serverForm.slug.trim() || !serverForm.name.trim()}
            >
              {editing ? t("common.save") : t("common.create")}
            </Button>
            <Button variant="default" onClick={() => requestServerLeave(closeServerModal)}>
              {t("common.cancel")}
            </Button>
          </Group>
        </Stack>
      </Stack>
    );
  }

  if (connectionModal !== null) {
    return (
      <Stack gap="md">
        <Group justify="space-between" align="center">
          <Title order={2}>
            {connectionModal.editing ? t("mcp.editConnection") : t("mcp.newConnection")}
          </Title>
          <Button variant="default" onClick={() => requestConnectionLeave(closeConnectionModal)}>
            {t("common.backToList")}
          </Button>
        </Group>
        <Stack gap="sm" maw={640}>
          <TextInput
            {...NO_AUTOFILL}
            label={t("common.slug")}
            placeholder="internal-docs"
            value={connectionForm.slug}
            onChange={(event) =>
              setConnectionForm({ ...connectionForm, slug: event.currentTarget.value })
            }
            disabled={Boolean(connectionModal.editing)}
            required
          />
          <TextInput
            {...NO_AUTOFILL}
            label={t("common.name")}
            value={connectionForm.name}
            onChange={(event) =>
              setConnectionForm({ ...connectionForm, name: event.currentTarget.value })
            }
            required
          />
          <TextInput
            {...NO_AUTOFILL}
            label={t("mcp.columns.url")}
            placeholder="https://mcp.example.com/mcp"
            value={connectionForm.url}
            onChange={(event) =>
              setConnectionForm({ ...connectionForm, url: event.currentTarget.value })
            }
            required
          />
          <Text size="xs" c="dimmed">
            {t("mcp.connectionUrlHint")}
          </Text>
          {!connectionModal.editing ? (
            <Button
              size="xs"
              variant="light"
              w="fit-content"
              onClick={() =>
                setConnectionForm({
                  ...connectionForm,
                  headers: '{\n  "Authorization": "Bearer "\n}',
                })
              }
            >
              {t("mcp.authTemplate")}
            </Button>
          ) : null}
          <Textarea
            {...NO_AUTOFILL}
            label={t("mcp.headersJson")}
            description={
              connectionModal.editing ? t("mcp.headersKeep") : t("mcp.headersExample")
            }
            value={connectionForm.headers}
            onChange={(event) =>
              setConnectionForm({ ...connectionForm, headers: event.currentTarget.value })
            }
            autosize
            minRows={2}
            maxRows={6}
          />
          <Group grow>
            <NumberInput
              {...NO_AUTOFILL}
              label={t("mcp.timeoutSec")}
              min={1}
              max={120}
              value={connectionForm.timeout_seconds}
              onChange={(value) =>
                setConnectionForm({
                  ...connectionForm,
                  timeout_seconds: typeof value === "number" ? value : 30,
                })
              }
            />
            <Switch
              label={t("mcp.enabledSwitch")}
              checked={connectionForm.enabled}
              onChange={(event) =>
                setConnectionForm({
                  ...connectionForm,
                  enabled: event.currentTarget.checked,
                })
              }
              mt="lg"
            />
          </Group>
          {formError ? (
            <Alert color="red" variant="light">
              {formError}
            </Alert>
          ) : null}
          <Group>
            <Button
              onClick={() => void saveConnection()}
              loading={busy === "connection-save"}
              disabled={
                !connectionForm.name.trim() ||
                !connectionForm.url.trim() ||
                (!connectionModal.editing && !connectionForm.slug.trim())
              }
            >
              {t("common.save")}
            </Button>
            <Button variant="default" onClick={() => requestConnectionLeave(closeConnectionModal)}>
              {t("common.cancel")}
            </Button>
          </Group>
        </Stack>
      </Stack>
    );
  }

  return (
    <Stack gap="md">
      <PageHeader title={t("mcp.title")}>
        <PageSearch value={pageSearch} onChange={setPageSearch} />
        <ViewToggle
          value={view}
          onChange={(value) => {
            setView(value);
            saveViewMode("mcp", value);
          }}
        />
        <IconAction
          kind="refresh"
          label={t("common.refresh")}
          onClick={() => {
            void loadServers();
            void loadConnections();
          }}
        />
        {tab === "servers" && isSuperadmin ? (
          <Button onClick={openServerModal} leftSection={<PlusIcon />}>
            {t("mcp.addServer")}
          </Button>
        ) : null}
        {tab === "connections" ? (
          <Button onClick={openCreateConnection} disabled={!canWrite} leftSection={<PlusIcon />}>
            {t("mcp.addConnection")}
          </Button>
        ) : null}
      </PageHeader>

      {error ? (
        <Alert color="red" title={t("common.error")}>
          {error}
        </Alert>
      ) : null}
      {notice ? (
        <Alert color="green" title={t("common.notice")} withCloseButton onClose={() => setNotice(null)}>
          {notice}
        </Alert>
      ) : null}

      <Tabs value={tab} onChange={setTab}>
        <Tabs.List>
          {isSuperadmin ? (
            <Tabs.Tab value="servers">{t("mcp.tabs.servers")}</Tabs.Tab>
          ) : null}
          <Tabs.Tab value="connections">{t("mcp.tabs.connections")}</Tabs.Tab>
        </Tabs.List>

        {isSuperadmin ? (
          <Tabs.Panel value="servers" pt="md">
            <Stack gap="md">
              <Text size="sm" c="dimmed">
                {t("mcp.serversIntro")}
              </Text>

              {issued ? (
                <Card withBorder>
                  <Stack gap="xs">
                    <Alert color="green" variant="light">
                      {t("mcp.keyOnce")}
                    </Alert>
                    <Code block style={{ whiteSpace: "pre-wrap" }}>
                      {clientConfig(issued.url, issued.apiKey)}
                    </Code>
                    <Group>
                      <Button
                        size="xs"
                        variant="default"
                        onClick={() => void copyText(clientConfig(issued.url, issued.apiKey))}
                      >
                        {t("mcp.copyConfig")}
                      </Button>
                      <Button size="xs" variant="subtle" onClick={() => setIssued(null)}>
                        {t("common.hide")}
                      </Button>
                    </Group>
                  </Stack>
                </Card>
              ) : null}

              <Card withBorder padding={0}>
                {serversLoading ? (
                  <Group justify="center" p="xl">
                    <Loader size="sm" />
                  </Group>
                ) : servers.length === 0 ? (
                  <Text p="xl" c="dimmed" size="sm">
                    {t("mcp.serversEmpty")}
                  </Text>
                ) : filteredServers.length === 0 ? (
                  <Text p="xl" c="dimmed" size="sm">
                    {t("common.emptyPageFilter")}
                  </Text>
                ) : view === "cards" ? (
                  <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }} spacing="md" p="md">
                    {filteredServers.map((server) => (
                      <Card key={server.id} withBorder>
                        <Stack gap="xs" h="100%">
                          <Group justify="space-between" align="flex-start" wrap="nowrap" gap="xs">
                            <Stack gap={2} style={{ minWidth: 0 }}>
                              <Text size="sm" fw={600} lineClamp={1}>
                                {server.name}
                              </Text>
                              <Code style={{ fontSize: 11 }}>{server.slug}</Code>
                            </Stack>
                            <Badge size="sm" color={server.enabled ? "green" : "red"}>
                              {server.enabled ? t("mcp.active") : t("mcp.inactive")}
                            </Badge>
                          </Group>
                          {server.description ? (
                            <Text size="xs" c="dimmed" lineClamp={2}>
                              {server.description}
                            </Text>
                          ) : null}
                          <Group gap={4} wrap="wrap">
                            {(server.agent_slugs ?? []).length === 0 ? (
                              <Text size="xs" c="dimmed">
                                {t("mcp.allowlistEmpty")}
                              </Text>
                            ) : (
                              (server.agent_slugs ?? []).slice(0, 4).map((slug) => (
                                <Badge key={slug} size="xs" variant="light" color="blue">
                                  {slug}
                                </Badge>
                              ))
                            )}
                            {(server.agent_slugs ?? []).length > 4 ? (
                              <Badge size="xs" variant="light" color="gray">
                                +{(server.agent_slugs ?? []).length - 4}
                              </Badge>
                            ) : null}
                          </Group>
                          <Group justify="space-between" mt="auto" align="center">
                            <Text size="xs" c="dimmed">
                              {formatDate(server.last_used_at)}
                            </Text>
                            <ServerActions
                              server={server}
                              busy={busy}
                              openEditServer={openEditServer}
                              toggleServer={toggleServer}
                              deleteServer={deleteServer}
                            />
                          </Group>
                        </Stack>
                      </Card>
                    ))}
                  </SimpleGrid>
                ) : (
                  <Table striped highlightOnHover withTableBorder verticalSpacing="sm">
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>{t("mcp.columns.name")}</Table.Th>
                        <Table.Th>{t("mcp.columns.slug")}</Table.Th>
                        <Table.Th>{t("mcp.columns.agents")}</Table.Th>
                        <Table.Th>{t("mcp.columns.status")}</Table.Th>
                        <Table.Th>{t("mcp.columns.used")}</Table.Th>
                        <Table.Th />
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {filteredServers.map((server) => (
                        <Table.Tr key={server.id}>
                          <Table.Td>
                            <Text size="sm">{server.name}</Text>
                            <Text size="xs" c="dimmed">
                              {server.description}
                            </Text>
                          </Table.Td>
                          <Table.Td>
                            <Code>{server.slug}</Code>
                          </Table.Td>
                          <Table.Td>
                            <Text size="xs">
                              {(server.agent_slugs ?? []).length === 0
                                ? t("common.emptyDash")
                                : (server.agent_slugs ?? []).join(", ")}
                            </Text>
                          </Table.Td>
                          <Table.Td>
                            <Badge size="sm" color={server.enabled ? "green" : "red"}>
                              {server.enabled ? t("mcp.active") : t("mcp.inactive")}
                            </Badge>
                          </Table.Td>
                          <Table.Td>
                            <Text size="xs">{formatDate(server.last_used_at)}</Text>
                          </Table.Td>
                          <Table.Td>
                            <ServerActions
                              server={server}
                              busy={busy}
                              openEditServer={openEditServer}
                              toggleServer={toggleServer}
                              deleteServer={deleteServer}
                            />
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                )}
              </Card>
            </Stack>
          </Tabs.Panel>
        ) : null}

        <Tabs.Panel value="connections" pt="md">
          <Stack gap="md">
            <Text size="sm" c="dimmed">
              {t("mcp.connectionsIntro")}
            </Text>

            {testResult ? (
              <Alert
                color={testResult.result.ok ? "green" : "red"}
                title={
                  testResult.result.ok
                    ? t("mcp.testOk", {
                        slug: testResult.slug,
                        count: testResult.result.tools.length,
                      })
                    : t("mcp.testFail", { slug: testResult.slug })
                }
                withCloseButton
                onClose={() => setTestResult(null)}
              >
                {testResult.result.ok ? (
                  <Stack gap={2}>
                    {testResult.result.tools.map((tool) => (
                      <Text key={tool.name} size="xs">
                        <Code>{tool.name}</Code> {tool.description}
                      </Text>
                    ))}
                  </Stack>
                ) : (
                  <Text size="xs">{testResult.result.error}</Text>
                )}
              </Alert>
            ) : null}

            <Card withBorder padding={0}>
              {connectionsLoading ? (
                <Group justify="center" p="xl">
                  <Loader size="sm" />
                </Group>
              ) : connections.length === 0 ? (
                <Text p="xl" c="dimmed" size="sm">
                  {t("mcp.connectionsEmpty")}
                </Text>
              ) : filteredConnections.length === 0 ? (
                <Text p="xl" c="dimmed" size="sm">
                  {t("common.emptyPageFilter")}
                </Text>
              ) : view === "cards" ? (
                <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }} spacing="md" p="md">
                  {filteredConnections.map((connection) => (
                    <Card key={connection.id} withBorder>
                      <Stack gap="xs" h="100%">
                        <Group justify="space-between" align="flex-start" wrap="nowrap" gap="xs">
                          <Stack gap={2} style={{ minWidth: 0 }}>
                            <Text size="sm" fw={600} lineClamp={1}>
                              {connection.name}
                            </Text>
                            <Code style={{ fontSize: 11 }}>{connection.slug}</Code>
                          </Stack>
                          <Badge size="sm" color={connection.enabled ? "green" : "red"}>
                            {connection.enabled ? t("mcp.enabledShort") : t("mcp.disabledShort")}
                          </Badge>
                        </Group>
                        <Text size="xs" c="dimmed" lineClamp={2} style={{ wordBreak: "break-all" }}>
                          {connection.url}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {connection.tools_cache.length
                            ? t("mcp.toolsCached", { count: connection.tools_cache.length })
                            : t("mcp.notTested")}
                        </Text>
                        <Group justify="space-between" mt="auto" align="center">
                          <Text size="xs" c="dimmed">
                            {connection.header_names.length
                              ? t("mcp.headersCount", { count: connection.header_names.length })
                              : t("mcp.noHeaders")}
                          </Text>
                          <ConnectionActions
                            connection={connection}
                            busy={busy}
                            canWrite={canWrite}
                            testConnection={testConnection}
                            openEditConnection={openEditConnection}
                            deleteConnection={deleteConnection}
                          />
                        </Group>
                      </Stack>
                    </Card>
                  ))}
                </SimpleGrid>
              ) : (
                <Table striped highlightOnHover withTableBorder verticalSpacing="sm">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>{t("mcp.columns.name")}</Table.Th>
                      <Table.Th>{t("mcp.columns.url")}</Table.Th>
                      <Table.Th>{t("mcp.columns.tools")}</Table.Th>
                      <Table.Th>{t("mcp.columns.status")}</Table.Th>
                      <Table.Th />
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {filteredConnections.map((connection) => (
                      <Table.Tr key={connection.id}>
                        <Table.Td>
                          <Text size="sm">{connection.name}</Text>
                          <Code>{connection.slug}</Code>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs" style={{ wordBreak: "break-all" }}>
                            {connection.url}
                          </Text>
                          <Text size="xs" c="dimmed">
                            {connection.header_names.length
                              ? t("mcp.headersList", {
                                  names: connection.header_names.join(", "),
                                })
                              : t("mcp.noHeaders")}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs">
                            {connection.tools_cache.length
                              ? `${connection.tools_cache.length} (${formatDate(connection.tools_cached_at)})`
                              : t("mcp.notTested")}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Badge size="sm" color={connection.enabled ? "green" : "red"}>
                            {connection.enabled ? t("mcp.enabledShort") : t("mcp.disabledShort")}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          <ConnectionActions
                            connection={connection}
                            busy={busy}
                            canWrite={canWrite}
                            testConnection={testConnection}
                            openEditConnection={openEditConnection}
                            deleteConnection={deleteConnection}
                          />
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
            </Card>
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
