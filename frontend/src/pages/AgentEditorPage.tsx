import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Anchor,
  Badge,
  Box,
  Breadcrumbs,
  Button,
  Card,
  Code,
  Collapse,
  Group,
  Loader,
  Modal,
  MultiSelect,
  NumberInput,
  ScrollArea,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { apiFetch, asItems, jsonBody } from "../api";
import { FIELD_ORDER, NO_AUTOFILL } from "../formAttrs";
import { useAssist, useAssistForm } from "../assist";
import { roleOf, useSession } from "../components/AppLayout";
import { formatDate, formatValue } from "../format";
import { Markdown } from "../components/Markdown";
import { ChevronDownIcon } from "../components/icons";
import { formatStreamEvent, streamedText, useRunStream } from "../useRunStream";
import type {
  Agent,
  AgentKind,
  AgentList,
  AgentMemory,
  AgentSuggestion,
  AgentUpsert,
  AgentVersion,
  AgentVisibility,
  Run,
  Skill,
  SkillList,
  ToolSpec,
  McpConnection,
  McpConnectionList,
  PreflightResult,
} from "../types";
import {
  ASSIST_AGENT_FIELDS_KEY,
  EMPTY_AGENT_FORM as EMPTY_FORM,
  formFromAgent,
  mergeAssistAgentFields,
  toNumber,
  type AgentFormState as FormState,
} from "./agents/agentForm";
import { useBaselineDirty, useUnsavedGuard } from "../unsavedChanges";

export function AgentEditorPage() {
  const { t } = useTranslation();
  const me = useSession();
  const canWrite = roleOf(me) !== "user";
  const { ref } = useParams<{ ref: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { openAssist } = useAssist();
  const isNew = !ref;

  const [agent, setAgent] = useState<Agent | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const { dirty, captureBaseline } = useBaselineDirty(form, canWrite);
  const [versions, setVersions] = useState<AgentVersion[]>([]);
  const [tools, setTools] = useState<ToolSpec[]>([]);
  const [mcpTools, setMcpTools] = useState<{ group: string; items: { value: string; label: string }[] }[]>(
    [],
  );
  const [skills, setSkills] = useState<Skill[]>([]);
  const [agentOptions, setAgentOptions] = useState<{ value: string; label: string }[]>([]);
  const [memories, setMemories] = useState<AgentMemory[]>([]);
  const [catalogReady, setCatalogReady] = useState(false);
  const [loading, setLoading] = useState(!isNew);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [publishVisibility, setPublishVisibility] = useState<AgentVisibility>("private");
  const [assistText, setAssistText] = useState("");
  const [suggestion, setSuggestion] = useState<AgentSuggestion | null>(null);
  const [rollbackTarget, setRollbackTarget] = useState<number | null>(null);
  const [purgeConfirm, setPurgeConfirm] = useState(false);
  const [testInput, setTestInput] = useState(() => t("agentEditor.defaultTestInput"));
  const [runId, setRunId] = useState<string | null>(null);
  const [preflight, setPreflight] = useState<PreflightResult | null>(null);
  const [llmOverrideOpen, setLlmOverrideOpen] = useState(false);
  const [preflightOpen, setPreflightOpen] = useState(false);
  const loadedRef = useRef<string | null>(null);
  const assistHandled = useRef(false);

  const { events, finished } = useRunStream(runId);

  useEffect(() => {
    const state = location.state as { assistMessage?: string } | null;
    if (!canWrite || !agent || !state?.assistMessage || assistHandled.current) {
      return;
    }
    assistHandled.current = true;
    openAssist({ message: state.assistMessage, mode: "form" });
    navigate(`${location.pathname}${location.search}`, {
      replace: true,
      state: null,
    });
  }, [agent, canWrite, location, navigate, openAssist]);

  // Инструменты: встроенные/кастомные + группы MCP; сохранённые ref'ы, которых нет в
  // разметке (выключенное подключение, пустой кеш), остаются отдельными опциями.
  const knownToolValues = useMemo(
    () => new Set([...tools.map((tool) => tool.name), ...mcpTools.flatMap((group) => group.items.map((item) => item.value))]),
    [tools, mcpTools],
  );
  const knownSkillValues = useMemo(() => new Set(skills.map((skill) => skill.slug)), [skills]);

  useAssistForm(
    "agent",
    {
      name: form.name,
      slug: form.slug,
      description: form.description,
      system_prompt: form.system_prompt,
      kind: form.kind,
      tools: form.tools,
      skills: form.skills,
      sub_agents: form.sub_agents,
      memory_enabled: form.memory_enabled,
      limits: { max_steps: form.max_steps, timeout_seconds: form.timeout_seconds, max_tokens: form.max_tokens, max_attempts: form.max_attempts, approval_mode: form.approval_mode },
      llm: { base_url: form.base_url, model: form.model, temperature: form.temperature },
    },
    (fields) => {
      const next = mergeAssistAgentFields(fields, {
        allowSlug: !agent,
        knownTools: knownToolValues,
        knownSkills: knownSkillValues,
      });
      if (Object.keys(next).length === 0) {
        return t("agentEditor.noFieldsFromModel");
      }
      setForm((prev) => ({ ...prev, ...next }));
      return null;
    },
  );

  useEffect(() => {
    setLlmOverrideOpen(Boolean(form.base_url || form.model));
  }, [agent?.slug]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!agent || !agent.memory_enabled) {
      setMemories([]);
      return;
    }
    let cancelled = false;
    apiFetch<AgentMemory[]>(
      `/v1/agents/${encodeURIComponent(agent.slug)}/memories`,
    )
      .then((value) => {
        if (!cancelled) {
          setMemories(value ?? []);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setMemories([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [agent?.slug, agent?.memory_enabled]);

  const removeMemory = async (memory: AgentMemory) => {
    if (!agent) {
      return;
    }
    try {
      await apiFetch<unknown>(
        `/v1/agents/${encodeURIComponent(agent.slug)}/memories/${encodeURIComponent(memory.id)}`,
        { method: "DELETE" },
      );
      setMemories((prev) => prev.filter((item) => item.id !== memory.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const toolOptions = useMemo(() => {
    const flat = tools.map((tool) => ({ value: tool.name, label: tool.name }));
    const known = new Set([
      ...flat.map((option) => option.value),
      ...mcpTools.flatMap((group) => group.items.map((item) => item.value)),
    ]);
    const orphans = form.tools
      .filter((name) => !known.has(name))
      .map((name) => ({ value: name, label: name }));
    return [
      { group: t("agentEditor.toolsGroupBuiltinHttp"), items: flat },
      ...mcpTools,
      ...(orphans.length ? [{ group: t("agentEditor.toolsGroupOther"), items: orphans }] : []),
    ];
  }, [tools, mcpTools, form.tools, t]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const [toolsResult, mcpResult, skillsResult, ownedAgents, sharedAgents] =
        await Promise.all([
          apiFetch<ToolSpec[]>("/v1/tools")
            .then((data) => asItems(data))
            .catch(() => [] as ToolSpec[]),
          apiFetch<McpConnectionList | McpConnection[]>("/v1/mcp-connections")
            .then((data) =>
              asItems(data)
                .filter((conn) => conn.enabled && conn.tools_cache.length > 0)
                .map((conn) => ({
                  group: `MCP: ${conn.name}`,
                  items: conn.tools_cache.map((tool) => ({
                    value: `mcp:${conn.slug}:${tool.name}`,
                    label: `${conn.slug}: ${tool.name}`,
                  })),
                })),
            )
            .catch(() => [] as { group: string; items: { value: string; label: string }[] }[]),
          apiFetch<SkillList | Skill[]>("/v1/skills")
            .then((data) => asItems(data))
            .catch(() => [] as Skill[]),
          apiFetch<AgentList>("/v1/agents?scope=owned&limit=200")
            .then((data) => asItems(data))
            .catch(() => [] as Agent[]),
          apiFetch<AgentList>("/v1/agents?scope=shared&limit=200")
            .then((data) => asItems(data))
            .catch(() => [] as Agent[]),
        ]);
      if (cancelled) {
        return;
      }
      setTools(toolsResult);
      setMcpTools(mcpResult);
      setSkills(skillsResult);
      const knownAgents = new Map<string, Agent>();
      for (const item of [...ownedAgents, ...sharedAgents]) {
        if (item.status === "published") {
          knownAgents.set(item.slug, item);
        }
      }
      setAgentOptions(
        [...knownAgents.values()].map((item) => ({
          value: item.slug,
          label: `${item.name} (${item.slug})`,
        })),
      );
      setCatalogReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Черновик с /agents (режим form ассистента) → применить после загрузки каталога.
  useEffect(() => {
    if (!isNew || !catalogReady) {
      return;
    }
    let raw: string | null = null;
    try {
      raw = sessionStorage.getItem(ASSIST_AGENT_FIELDS_KEY);
      if (raw) {
        sessionStorage.removeItem(ASSIST_AGENT_FIELDS_KEY);
      }
    } catch {
      return;
    }
    if (!raw) {
      return;
    }
    try {
      const fields = JSON.parse(raw) as Record<string, unknown>;
      const next = mergeAssistAgentFields(fields, {
        allowSlug: true,
        knownTools: knownToolValues,
        knownSkills: knownSkillValues,
      });
      if (Object.keys(next).length === 0) {
        return;
      }
      setForm((prev) => {
        const merged = { ...prev, ...next };
        captureBaseline(merged);
        return merged;
      });
      setNotice(t("assist.appliedNotice"));
    } catch {
      // ignore bad draft
    }
  }, [
    isNew,
    catalogReady,
    knownToolValues,
    knownSkillValues,
    captureBaseline,
    t,
  ]);

  const reloadAgent = useCallback(async (slug: string): Promise<Agent> => {
    const value = await apiFetch<Agent>(`/v1/agents/${encodeURIComponent(slug)}`);
    loadedRef.current = slug;
    setAgent(value);
    const next = formFromAgent(value);
    setForm(next);
    captureBaseline(next);
    setPublishVisibility(value.visibility);
    return value;
  }, [captureBaseline]);

  const applyAgent = useCallback((value: Agent) => {
    setAgent(value);
    const next = formFromAgent(value);
    setForm(next);
    captureBaseline(next);
    setPublishVisibility(value.visibility);
    void apiFetch<AgentVersion[] | { items: AgentVersion[] }>(
      `/v1/agents/${encodeURIComponent(value.slug)}/versions`,
    )
      .then((data) => setVersions(asItems(data)))
      .catch(() => setVersions([]));
  }, [captureBaseline]);

  useEffect(() => {
    if (!ref) {
      setAgent(null);
      setForm(EMPTY_FORM);
      captureBaseline(EMPTY_FORM);
      setVersions([]);
      loadedRef.current = null;
      setLoading(false);
      return;
    }
    if (loadedRef.current === ref) {
      return;
    }
    let alive = true;
    setLoading(true);
    setError(null);
    apiFetch<Agent>(`/v1/agents/${encodeURIComponent(ref)}`)
      .then((value) => {
        if (!alive) {
          return;
        }
        loadedRef.current = ref;
        applyAgent(value);
      })
      .catch((err: unknown) => {
        if (alive) {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (alive) {
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [ref, applyAgent, captureBaseline]);

  const setField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const collectPayload = (): AgentUpsert => ({
    slug: form.slug.trim(),
    name: form.name.trim(),
    description: form.description,
    kind: form.kind,
    plugin_name: form.kind === "plugin" ? form.plugin_name.trim() || null : null,
    system_prompt: form.system_prompt,
    tools: form.tools,
    skills: form.skills,
    sub_agents: form.sub_agents,
    memory_enabled: form.memory_enabled,
    llm: {
      base_url: form.base_url.trim() || null,
      model: form.model.trim() || null,
      temperature: toNumber(form.temperature),
    },
    limits: {
      max_steps: toNumber(form.max_steps) ?? 8,
      timeout_seconds: toNumber(form.timeout_seconds) ?? 120,
      ...(toNumber(form.max_tokens) !== null
        ? { max_tokens: toNumber(form.max_tokens) as number }
        : {}),
      ...(toNumber(form.max_attempts) !== null
        ? { max_attempts: toNumber(form.max_attempts) as number }
        : {}),
      approval_mode: form.approval_mode,
    },
  });

  const currentRef = agent ? agent.slug : ref;

  const runAction = async (key: string, action: () => Promise<void>) => {
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

  const persistAgent = async () => {
    const payload = collectPayload();
    if (!payload.name) {
      throw new Error(t("agentEditor.nameRequired"));
    }
    if (!payload.slug) {
      throw new Error(t("agentEditor.slugRequired"));
    }
    if (isNew) {
      const created = await apiFetch<Agent>("/v1/agents", {
        method: "POST",
        body: jsonBody(payload),
      });
      captureBaseline(formFromAgent(created));
      setNotice(t("agentEditor.created"));
      navigate(`/agents/${encodeURIComponent(created.slug)}`, { replace: true });
      return;
    }
    const { slug: _slug, ...patch } = payload;
    await apiFetch<unknown>(`/v1/agents/${encodeURIComponent(String(currentRef))}`, {
      method: "PATCH",
      body: jsonBody(patch),
    });
    await reloadAgent(String(currentRef));
    setNotice(t("agentEditor.saved"));
  };

  const { requestLeave } = useUnsavedGuard(
    "agent-editor",
    canWrite && dirty,
    canWrite
      ? async () => {
          setError(null);
          try {
            await persistAgent();
          } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
            throw err;
          }
        }
      : undefined,
  );

  const handleSave = () => runAction("save", persistAgent);

  const handleAssist = () =>
    runAction("assist", async () => {
      const description = assistText.trim();
      if (description.length < 3) {
        throw new Error(t("agentEditor.describeRequired"));
      }
      const result = await apiFetch<AgentSuggestion>("/v1/assist/agent", {
        method: "POST",
        body: jsonBody({ description }),
      });
      setSuggestion(result);
      setForm((prev) => ({
        ...prev,
        name: result.name || prev.name,
        slug: prev.slug || result.slug,
        description: result.description || prev.description,
        system_prompt: result.system_prompt || prev.system_prompt,
        tools: result.tools,
        skills: result.skills,
      }));
      setNotice(t("agentEditor.filledNotice"));
    });

  const handlePublish = () =>
    runAction("publish", async () => {
      if (!currentRef) {
        throw new Error(t("agentEditor.saveFirst"));
      }
      await apiFetch<unknown>(`/v1/agents/${encodeURIComponent(currentRef)}/publish`, {
        method: "POST",
        body: jsonBody({ visibility: publishVisibility }),
      });
      const updated = await reloadAgent(currentRef);
      applyAgent(updated);
      setNotice(t("agentEditor.publishedNotice", { visibility: updated.visibility }));
    });

  const handleClone = () =>
    runAction("clone", async () => {
      if (!currentRef) {
        throw new Error(t("agentEditor.saveFirst"));
      }
      const created = await apiFetch<Agent>(`/v1/agents/${encodeURIComponent(currentRef)}/clone`, {
        method: "POST",
      });
      if (created && created.slug) {
        setNotice(t("agentEditor.cloned", { name: created.name }));
        navigate(`/agents/${encodeURIComponent(created.slug)}`);
        return;
      }
      navigate("/agents");
    });

  const handleRollback = (version: number) =>
    runAction("rollback", async () => {
      if (!currentRef) {
        throw new Error(t("agentEditor.saveFirst"));
      }
      const rolled = await apiFetch<Agent>(
        `/v1/agents/${encodeURIComponent(currentRef)}/rollback`,
        { method: "POST", body: jsonBody({ version }) },
      );
      applyAgent(rolled);
      setRollbackTarget(null);
      setNotice(
        t("agentEditor.rolledBack", {
          version,
          published: rolled.published_version,
        }),
      );
    });

  const handleArchive = () =>
    runAction("archive", async () => {
      if (!currentRef) {
        throw new Error(t("agentEditor.saveFirst"));
      }
      const archived = await apiFetch<Agent>(`/v1/agents/${encodeURIComponent(currentRef)}`, {
        method: "DELETE",
      });
      applyAgent(archived);
      setNotice(t("agentEditor.archived"));
    });

  const handlePurge = () =>
    runAction("purge", async () => {
      if (!currentRef) {
        throw new Error(t("agentEditor.saveFirst"));
      }
      if (agent?.status !== "archived") {
        throw new Error(t("agentEditor.purgeOnlyArchive"));
      }
      await apiFetch<void>(`/v1/agents/${encodeURIComponent(currentRef)}`, {
        method: "DELETE",
      });
      setPurgeConfirm(false);
      navigate("/agents");
    });

  const isStreaming = runId !== null && !finished;
  const canRun = Boolean(agent && agent.status === "published" && testInput.trim()) && !isStreaming;

  const handleTestRun = () =>
    runAction("run", async () => {
      if (!agent) {
        throw new Error(t("agentEditor.saveFirst"));
      }
      const run = await apiFetch<Run>("/v1/runs", {
        method: "POST",
        body: jsonBody({ agent_id: agent.id, input: testInput }),
      });
      setRunId(run.run_id);
    });

  const handlePreflight = () =>
    runAction("preflight", async () => {
      if (!agent) {
        throw new Error(t("agentEditor.saveFirst"));
      }
      const result = await apiFetch<PreflightResult>("/v1/runs/preflight", {
        method: "POST",
        body: jsonBody({ agent_id: agent.slug }),
      });
      setPreflight(result);
      setPreflightOpen(true);
    });

  const streamText = streamedText(events);
  const completedEvent = events.find((event) => event.event === "run.completed");
  const failedEvent = events.find((event) => event.event === "run.failed");
  const cancelled = events.some((event) => event.event === "run.cancelled");

  const statusLabel =
    agent?.status === "draft" || agent?.status === "published" || agent?.status === "archived"
      ? t(`common.${agent.status}`)
      : agent?.status;

  if (loading) {
    return (
      <Group justify="center" p="xl">
        <Loader size="sm" />
      </Group>
    );
  }

  return (
    <Stack gap="md">
      <Breadcrumbs separator="→" fz="sm">
        <Anchor component={Link} to="/agents" c="dimmed">
          {t("agents.title")}
        </Anchor>
        <Text c="dimmed">{isNew ? t("agentEditor.breadcrumbNew") : form.name || form.slug}</Text>
      </Breadcrumbs>
      <Group justify="space-between" align="center">
        <Group gap="sm">
          <Title order={2}>{isNew ? t("agentEditor.titleNew") : form.name || form.slug}</Title>
          {agent ? (
            <Badge color={agent.status === "published" ? "green" : agent.status === "archived" ? "red" : "gray"}>
              {statusLabel}
            </Badge>
          ) : null}
          {agent?.published_version ? (
            <Badge variant="light">v{agent.published_version}</Badge>
          ) : null}
          {agent?.skills_stale ? (
            <Badge variant="light" color="orange" title={t("agents.staleSkillsTitle")}>
              {t("agents.staleSkills")}
            </Badge>
          ) : null}
          {agent?.tools_stale ? (
            <Badge variant="light" color="grape" title={t("agents.staleToolsTitle")}>
              {t("agents.staleTools")}
            </Badge>
          ) : null}
        </Group>
        <Button variant="default" onClick={() => requestLeave(() => navigate("/agents"))}>
          {t("common.backToList")}
        </Button>
      </Group>

      {error ? (
        <Alert color="red" title={t("common.error")}>
          {error}
        </Alert>
      ) : null}
      {notice ? <Alert color="green">{notice}</Alert> : null}
      {agent?.skills_stale || agent?.tools_stale ? (
        <Alert color="orange" title={t("agentEditor.staleSnapshotTitle")}>
          {t("agentEditor.staleSnapshotBody", {
            version: agent?.published_version ? ` v${agent.published_version}` : "",
          })}
        </Alert>
      ) : null}
      {!canWrite ? (
        <Alert color="gray" title={t("common.viewOnly")}>
          {t("agentEditor.viewOnlyBody")}
        </Alert>
      ) : null}

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
        <Stack gap="md">
          <Card withBorder>
            <Stack gap="sm">
              <Text fw={600}>{t("agentEditor.aiTitle")}</Text>
              <Text size="xs" c="dimmed">
                {t("agentEditor.aiHint")}
              </Text>
              <Textarea {...NO_AUTOFILL}
                placeholder={t("agentEditor.aiPlaceholder")}
                value={assistText}
                onChange={(event) => setAssistText(event.currentTarget.value)}
                minRows={2}
                autosize
              />
              <Group>
                <Button
                  variant="light"
                  onClick={() => void handleAssist()}
                  loading={busy === "assist"}
                  disabled={!canWrite}
                >
                  {t("common.generate")}
                </Button>
              </Group>
              {suggestion ? (
                <Stack gap={4}>
                  {suggestion.notes ? (
                    <Text size="xs" c="dimmed">
                      {suggestion.notes}
                    </Text>
                  ) : null}
                  {suggestion.new_tools.length > 0 ? (
                    <Text size="xs" c="dimmed">
                      {t("agentEditor.missingTools", {
                        list: suggestion.new_tools
                          .map((tool) => `${tool.slug} (${tool.name})`)
                          .join(", "),
                      })}
                    </Text>
                  ) : null}
                  {suggestion.warnings.map((warning) => (
                    <Text key={warning} size="xs" c="orange">
                      {warning}
                    </Text>
                  ))}
                </Stack>
              ) : null}
            </Stack>
          </Card>

          <Card withBorder>
            <Stack gap="sm">
              <Text fw={600}>{t("agentEditor.basics")}</Text>
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <TextInput
                  {...NO_AUTOFILL}
                  inputWrapperOrder={[...FIELD_ORDER]}
                  label={t("common.name")}
                  value={form.name}
                  onChange={(event) => setField("name", event.currentTarget.value)}
                  required
                />
                <TextInput
                  {...NO_AUTOFILL}
                  inputWrapperOrder={[...FIELD_ORDER]}
                  label={t("common.slug")}
                  description={isNew ? t("common.slugHint") : t("common.slugImmutable")}
                  value={form.slug}
                  onChange={(event) => setField("slug", event.currentTarget.value)}
                  readOnly={!isNew}
                  required
                />
              </SimpleGrid>
              <Textarea {...NO_AUTOFILL}
                label={t("common.description")}
                value={form.description}
                onChange={(event) => setField("description", event.currentTarget.value)}
                minRows={2}
                autosize
              />
              {form.kind === "preset" ? (
                <Textarea {...NO_AUTOFILL}
                  label={t("agentEditor.systemPrompt")}
                  value={form.system_prompt}
                  onChange={(event) => setField("system_prompt", event.currentTarget.value)}
                  minRows={6}
                  autosize
                />
              ) : null}
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <Select
                  label={t("agentEditor.kind")}
                  description={
                    form.kind === "preset"
                      ? t("agentEditor.kindPresetHint")
                      : t("agentEditor.kindPluginHint")
                  }
                  data={[
                    { value: "preset", label: t("agentEditor.kindPreset") },
                    { value: "plugin", label: t("agentEditor.kindPlugin") },
                  ]}
                  value={form.kind}
                  onChange={(value) => {
                    const kind = (value as AgentKind | null) ?? "preset";
                    setForm((prev) => ({
                      ...prev,
                      kind,
                      ...(kind === "plugin"
                        ? {
                            tools: [],
                            skills: [],
                            sub_agents: [],
                            memory_enabled: false,
                          }
                        : {}),
                    }));
                  }}
                  allowDeselect={false}
                />
                {form.kind === "plugin" ? (
                  <TextInput {...NO_AUTOFILL}
                    label={t("agentEditor.pluginName")}
                    description={t("agentEditor.pluginHint")}
                    value={form.plugin_name}
                    onChange={(event) => setField("plugin_name", event.currentTarget.value)}
                  />
                ) : null}
              </SimpleGrid>
              {form.kind === "plugin" ? (
                <Alert color="blue">{t("agentEditor.pluginAlert")}</Alert>
              ) : (
                <>
                  <MultiSelect
                    label={t("agentEditor.tools")}
                    description={t("agentEditor.toolsHint")}
                    data={toolOptions}
                    value={form.tools}
                    onChange={(value) => setField("tools", value)}
                    searchable
                    clearable
                    nothingFoundMessage={t("agentEditor.toolsNotFound")}
                  />
                  <MultiSelect
                    label={t("agentEditor.skills")}
                    description={t("agentEditor.skillsHint")}
                    data={skills.map((skill) => ({ value: skill.slug, label: skill.name || skill.slug }))}
                    value={form.skills}
                    onChange={(value) => setField("skills", value)}
                    searchable
                    clearable
                    nothingFoundMessage={t("agentEditor.skillsNotFound")}
                  />
                  <MultiSelect
                    label={t("agentEditor.subAgents")}
                    description={t("agentEditor.subAgentsHint")}
                    data={agentOptions.filter((item) => item.value !== form.slug)}
                    value={form.sub_agents}
                    onChange={(value) => setField("sub_agents", value)}
                    searchable
                    clearable
                  />
                  <Switch
                    label={t("agentEditor.memoryEnabled")}
                    description={t("agentEditor.memoryHint")}
                    checked={form.memory_enabled}
                    onChange={(event) =>
                      setField("memory_enabled", event.currentTarget.checked)
                    }
                  />
                </>
              )}
            </Stack>
          </Card>

          <Card withBorder>
            <Stack gap="sm">
              <Text fw={600}>{t("agentEditor.llm")}</Text>
              <Text size="xs" c="dimmed">
                {t("agentEditor.llmGlobalHint")}
              </Text>
              <NumberInput {...NO_AUTOFILL}
                label={t("agentEditor.temperature")}
                description={t("agentEditor.temperatureHint")}
                min={0}
                max={1}
                step={0.1}
                decimalScale={2}
                value={form.temperature}
                onChange={(value) => setField("temperature", value)}
              />
              <Button
                variant="subtle"
                size="compact-sm"
                onClick={() => setLlmOverrideOpen((open) => !open)}
                aria-expanded={llmOverrideOpen}
              >
                <Group gap={6} wrap="nowrap">
                  {t("agentEditor.llmOverride")}
                  <Box
                    style={{
                      transform: llmOverrideOpen ? "rotate(0deg)" : "rotate(-90deg)",
                      transition: "transform 120ms ease",
                      display: "flex",
                    }}
                  >
                    <ChevronDownIcon />
                  </Box>
                </Group>
              </Button>
              <Collapse expanded={llmOverrideOpen}>
                <Stack gap="sm">
                  <TextInput {...NO_AUTOFILL}
                    label="base_url"
                    description={t("agentEditor.llmGlobalHint")}
                    placeholder="http://localhost:11434/v1"
                    value={form.base_url}
                    onChange={(event) => setField("base_url", event.currentTarget.value)}
                  />
                  <TextInput {...NO_AUTOFILL}
                    label={t("agentEditor.model")}
                    description={t("agentEditor.llmGlobalHint")}
                    value={form.model}
                    onChange={(event) => setField("model", event.currentTarget.value)}
                  />
                </Stack>
              </Collapse>
            </Stack>
          </Card>

          <Card withBorder>
            <Stack gap="sm">
              <Text fw={600}>{t("agentEditor.limits")}</Text>
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <NumberInput {...NO_AUTOFILL}
                  label="max_steps"
                  min={1}
                  max={100}
                  value={form.max_steps}
                  onChange={(value) => setField("max_steps", value)}
                />
                <NumberInput {...NO_AUTOFILL}
                  label="timeout_seconds"
                  min={1}
                  max={3600}
                  value={form.timeout_seconds}
                  onChange={(value) => setField("timeout_seconds", value)}
                />
                <NumberInput {...NO_AUTOFILL}
                  label="max_tokens"
                  min={1}
                  max={2000000}
                  placeholder="200000"
                  value={form.max_tokens}
                  onChange={(value) => setField("max_tokens", value)}
                />
                <NumberInput {...NO_AUTOFILL}
                  label="max_attempts"
                  min={1}
                  max={5}
                  placeholder="2"
                  value={form.max_attempts}
                  onChange={(value) => setField("max_attempts", value)}
                />
              </SimpleGrid>
              <Select
                label={t("agentEditor.approvalMode")}
                description={t("agentEditor.approvalHint")}
                data={[
                  { value: "mutating", label: t("agentEditor.approvalModes.mutating") },
                  { value: "all", label: t("agentEditor.approvalModes.all") },
                  { value: "never", label: t("agentEditor.approvalModes.never") },
                ]}
                value={form.approval_mode}
                onChange={(value) => setField("approval_mode", value ?? "mutating")}
              />
            </Stack>
          </Card>

          <Group>
            <Button
              onClick={() => void handleSave()}
              loading={busy === "save"}
              disabled={!canWrite}
            >
              {t("common.save")}
            </Button>
            <Button
              variant="light"
              onClick={() => void handleClone()}
              loading={busy === "clone"}
              disabled={isNew || !canWrite}
            >
              {t("agentEditor.clone")}
            </Button>
            {agent?.status === "archived" ? (
              <Button
                variant="light"
                color="red"
                onClick={() => setPurgeConfirm(true)}
                disabled={!canWrite}
              >
                {t("agentEditor.purge")}
              </Button>
            ) : (
              <Button
                variant="light"
                color="red"
                onClick={() => void handleArchive()}
                loading={busy === "archive"}
                disabled={isNew || !canWrite}
              >
                {t("agentEditor.archive")}
              </Button>
            )}
          </Group>
        </Stack>

        <Stack gap="md">
          {agent?.memory_enabled ? (
            <Card withBorder>
              <Stack gap="sm">
                <Text fw={600}>{t("agentEditor.memory")}</Text>
                {memories.length === 0 ? (
                  <Text size="sm" c="dimmed">
                    {t("agentEditor.memoryEmpty")}
                  </Text>
                ) : (
                  <Table.ScrollContainer minWidth={620}>
                    <Table withTableBorder withColumnBorders>
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>{t("agentEditor.memoryKey")}</Table.Th>
                          <Table.Th>{t("agentEditor.memoryContent")}</Table.Th>
                          <Table.Th>{t("agentEditor.memoryTags")}</Table.Th>
                          <Table.Th>{t("agentEditor.memoryUpdated")}</Table.Th>
                          <Table.Th />
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {memories.map((memory) => (
                          <Table.Tr key={memory.id}>
                            <Table.Td>
                              <Text size="sm" ff="monospace">
                                {memory.key}
                              </Text>
                            </Table.Td>
                            <Table.Td>
                              <Text size="sm" lineClamp={3}>
                                {memory.content}
                              </Text>
                            </Table.Td>
                            <Table.Td>
                              <Text size="xs">{memory.tags.join(", ") || "—"}</Text>
                            </Table.Td>
                            <Table.Td>
                              <Text size="xs">{formatDate(memory.updated_at)}</Text>
                            </Table.Td>
                            <Table.Td>
                              <Button
                                size="compact-xs"
                                variant="subtle"
                                color="red"
                                onClick={() => void removeMemory(memory)}
                              >
                                {t("common.delete")}
                              </Button>
                            </Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Table.ScrollContainer>
                )}
              </Stack>
            </Card>
          ) : null}
          <Card withBorder>
            <Stack gap="sm">
              <Text fw={600}>{t("agentEditor.publishSection")}</Text>
              <SegmentedControl
                value={publishVisibility}
                onChange={(value) => setPublishVisibility(value as AgentVisibility)}
                data={[
                  { label: t("agentEditor.visibilityPrivate"), value: "private" },
                  { label: t("agentEditor.visibilityShared"), value: "shared" },
                ]}
              />
              <Group justify="space-between">
                <Button
                  onClick={() => void handlePublish()}
                  loading={busy === "publish"}
                  disabled={isNew || !canWrite}
                >
                  {t("agentEditor.publish")}
                </Button>
                <Text size="xs" c="dimmed">
                  {agent?.published_version
                    ? t("agentEditor.publishedVersion", { version: agent.published_version })
                    : t("agentEditor.neverPublished")}
                </Text>
              </Group>
            </Stack>
          </Card>

          <Card withBorder>
            <Stack gap="sm">
              <Text fw={600}>{t("agentEditor.versions")}</Text>
              {versions.length === 0 ? (
                <Text size="sm" c="dimmed">
                  {t("agentEditor.noVersions")}
                </Text>
              ) : (
                <Table withTableBorder verticalSpacing="xs">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>{t("agentEditor.versionCol")}</Table.Th>
                      <Table.Th>{t("agentEditor.createdCol")}</Table.Th>
                      <Table.Th>{t("agentEditor.authorCol")}</Table.Th>
                      <Table.Th />
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {[...versions]
                      .sort((a, b) => b.version - a.version)
                      .map((version) => {
                        const isCurrent = version.version === agent?.published_version;
                        return (
                          <Table.Tr key={version.id ?? version.version}>
                            <Table.Td>
                              v{version.version}
                              {isCurrent ? (
                                <Badge ml={6} size="xs" variant="light" color="green">
                                  {t("agentEditor.current")}
                                </Badge>
                              ) : null}
                            </Table.Td>
                            <Table.Td>{formatDate(version.created_at)}</Table.Td>
                            <Table.Td>
                              <Text size="xs" c="dimmed">
                                {version.created_by ?? t("common.emptyDash")}
                              </Text>
                            </Table.Td>
                            <Table.Td>
                              <Button
                                size="compact-xs"
                                variant="light"
                                disabled={!canWrite || isCurrent || version.version === rollbackTarget}
                                onClick={() => setRollbackTarget(version.version)}
                              >
                                {t("agentEditor.rollback")}
                              </Button>
                            </Table.Td>
                          </Table.Tr>
                        );
                      })}
                  </Table.Tbody>
                </Table>
              )}
            </Stack>
          </Card>

          <Card withBorder>
            <Stack gap="sm">
              <Text fw={600}>{t("agentEditor.testRun")}</Text>
              {agent && agent.status !== "published" ? (
                <Alert color="yellow" variant="light">
                  {t("agentEditor.publishFirst")}
                </Alert>
              ) : null}
              <Textarea {...NO_AUTOFILL}
                label={t("agentEditor.input")}
                value={testInput}
                onChange={(event) => setTestInput(event.currentTarget.value)}
                minRows={3}
                autosize
              />
              <Group>
                <Button
                  onClick={() => void handleTestRun()}
                  disabled={!canRun}
                  loading={busy === "run"}
                >
                  {t("agentEditor.run")}
                </Button>
                <Button
                  variant="default"
                  onClick={() => void handlePreflight()}
                  disabled={!agent || !canWrite}
                  loading={busy === "preflight"}
                >
                  {t("agentEditor.preflight")}
                </Button>
                {runId ? (
                  <Text size="xs" c="dimmed" ff="monospace">
                    {runId}
                  </Text>
                ) : null}
              </Group>

              {events.length > 0 || runId ? (
                <Stack gap="xs">
                  <Group gap="xs">
                    <Badge size="sm" color={finished ? (failedEvent ? "red" : "green") : "blue"}>
                      {finished
                        ? failedEvent
                          ? "failed"
                          : cancelled
                            ? "cancelled"
                            : "succeeded"
                        : "stream"}
                    </Badge>
                    <Text size="xs" c="dimmed">
                      {t("agentEditor.eventsCount", { count: events.length })}
                    </Text>
                  </Group>
                  {!completedEvent && streamText ? <Markdown>{streamText}</Markdown> : null}
                  {completedEvent ? (
                    <Markdown>{formatValue(completedEvent.data.output)}</Markdown>
                  ) : null}
                  {failedEvent ? (
                    <Alert color="red" variant="light">
                      {String(failedEvent.data.error ?? t("agentEditor.runFailed"))}
                    </Alert>
                  ) : null}
                  <ScrollArea h={240} type="auto">
                    <Code block style={{ whiteSpace: "pre-wrap", fontSize: 11 }}>
                      {events.map(formatStreamEvent).join("\n")}
                    </Code>
                  </ScrollArea>
                </Stack>
              ) : null}
            </Stack>
          </Card>
        </Stack>
      </SimpleGrid>

      <Modal
        opened={rollbackTarget !== null}
        onClose={() => setRollbackTarget(null)}
        title={t("agentEditor.rollbackTitle", { version: rollbackTarget ?? "" })}
        size="sm"
      >
        <Stack gap="sm">
          <Text size="sm">
            {t("agentEditor.rollbackBody", { version: rollbackTarget })}
          </Text>
          <Text size="xs" c="dimmed">
            {t("agentEditor.rollbackToolsNote")}
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setRollbackTarget(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              onClick={() => rollbackTarget !== null && void handleRollback(rollbackTarget)}
              loading={busy === "rollback"}
            >
              {t("agentEditor.rollback")}
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Modal
        opened={purgeConfirm}
        onClose={() => setPurgeConfirm(false)}
        title={t("agentEditor.purgeTitle", {
          name: agent?.name || agent?.slug || t("agentEditor.agentFallback"),
        })}
        size="sm"
      >
        <Stack gap="sm">
          <Text size="sm">{t("agentEditor.purgeBody")}</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setPurgeConfirm(false)}>
              {t("common.cancel")}
            </Button>
            <Button color="red" onClick={() => void handlePurge()} loading={busy === "purge"}>
              {t("common.delete")}
            </Button>
          </Group>
        </Stack>
      </Modal>
      <Modal
        opened={preflightOpen}
        onClose={() => setPreflightOpen(false)}
        title={t("agentEditor.preflightTitle")}
        size="lg"
      >
        <Stack gap="sm">
          {preflight ? (
            <>
              <Badge color={preflight.ok ? "green" : "red"} variant="light">
                {preflight.ok
                  ? t("agentEditor.preflightOk")
                  : t("agentEditor.preflightFailed")}
              </Badge>
              <Table withTableBorder withColumnBorders>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t("agentEditor.preflightCheck")}</Table.Th>
                    <Table.Th>{t("agentEditor.preflightStatus")}</Table.Th>
                    <Table.Th>{t("agentEditor.preflightMessage")}</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {preflight.checks.map((check) => (
                    <Table.Tr key={check.id}>
                      <Table.Td>
                        {t(`agentEditor.preflightChecks.${check.id}`)}
                      </Table.Td>
                      <Table.Td>
                        <Badge
                          size="sm"
                          color={
                            check.status === "ok"
                              ? "green"
                              : check.status === "warn"
                                ? "yellow"
                                : check.status === "error"
                                  ? "red"
                                  : "gray"
                          }
                          variant="light"
                        >
                          {check.status}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{check.message}</Text>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
              <Stack gap={4}>
                <Text fw={600} size="sm">
                  {t("agentEditor.preflightEffective")}
                </Text>
                <Text size="sm">
                  {t("agentEditor.preflightModel")}:{" "}
                  <Text span ff="monospace">
                    {preflight.effective.model ?? t("common.emptyDash")}
                  </Text>
                </Text>
                <Text size="sm">
                  {t("agentEditor.preflightBaseUrl")}:{" "}
                  <Text span ff="monospace">
                    {preflight.effective.base_url ?? t("common.emptyDash")}
                  </Text>
                </Text>
                <Text size="sm">
                  max_steps={preflight.effective.max_steps}, timeout=
                  {preflight.effective.timeout_seconds}s, max_tokens=
                  {preflight.effective.max_tokens}, max_attempts=
                  {preflight.effective.max_attempts}, approval=
                  {preflight.effective.approval_mode}
                </Text>
                <Text size="sm">
                  {t("runDetail.harnessTools")}: {preflight.effective.tools.length} ·{" "}
                  {t("runDetail.harnessSkills")}: {preflight.effective.skills.length} ·{" "}
                  {t("runDetail.harnessMcp")}: {preflight.effective.mcp.length} ·{" "}
                  {t("agentEditor.subAgents")}: {preflight.effective.sub_agents.length}
                </Text>
              </Stack>
              <Text size="xs" c="dimmed">
                {t("agentEditor.preflightVersionNote", {
                  version: preflight.effective.agent_version ?? "—",
                })}
              </Text>
            </>
          ) : null}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setPreflightOpen(false)}>
              {t("agentEditor.preflightClose")}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
