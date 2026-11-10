import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActionIcon,
  Alert,
  Box,
  Button,
  Card,
  Code,
  Group,
  Loader,
  MultiSelect,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Tooltip,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import type { ComboboxItem, ComboboxLikeRenderOptionInput } from "@mantine/core";
import { apiFetch, asItems, buildQuery, jsonBody } from "../api";
import { NO_AUTOFILL } from "../formAttrs";
import { AllowlistMultiSelect } from "../components/AllowlistMultiSelect";
import { CheckIcon, TrashIcon } from "../components/icons";
import { useSession } from "../components/AppLayout";
import { PageHeader, PageSearch } from "../components/PageHeader";
import { formatDate } from "../format";
import { notifySuccess } from "../notify";
import {
  SERVICE_KEY_SCOPE_PRESETS,
  SERVICE_KEY_SCOPES,
  type Agent,
  type AgentList,
  type ServiceKey,
  type ServiceKeyCreated,
  type ServiceKeyScopePreset,
  type SkillList,
  type ToolSpec,
} from "../types";
import { useAssistForm } from "../assist";
import { matchesPageSearch } from "../pageSearch";
import { useBaselineDirty, useUnsavedGuard } from "../unsavedChanges";

const SCOPE_PRESET_ORDER: ServiceKeyScopePreset[] = ["consume", "manage", "full"];

type KeyDraft = {
  name: string;
  scopes: string[];
  agent_slugs: string[];
  tool_slugs: string[];
  skill_slugs: string[];
};

type KeyPatch = Omit<KeyDraft, "name">;

function patchFromKey(key: ServiceKey): KeyPatch {
  return {
    scopes: [...key.scopes],
    agent_slugs: [...(key.agent_slugs ?? [])],
    tool_slugs: [...(key.tool_slugs ?? [])],
    skill_slugs: [...(key.skill_slugs ?? [])],
  };
}

const EMPTY_DRAFT: KeyDraft = {
  name: "",
  scopes: [...SERVICE_KEY_SCOPE_PRESETS.consume],
  agent_slugs: [],
  tool_slugs: [],
  skill_slugs: [],
};

function scopeI18nKey(scope: string): string {
  return scope.replace(":", "_");
}

function scopesEqual(a: readonly string[], b: readonly string[]): boolean {
  if (a.length !== b.length) return false;
  const set = new Set(a);
  return b.every((scope) => set.has(scope));
}

function activeScopePreset(scopes: readonly string[]): ServiceKeyScopePreset | null {
  for (const id of SCOPE_PRESET_ORDER) {
    if (scopesEqual(scopes, SERVICE_KEY_SCOPE_PRESETS[id])) return id;
  }
  return null;
}

export function ServiceKeysPage() {
  const { t } = useTranslation();
  const me = useSession();
  const [keys, setKeys] = useState<ServiceKey[]>([]);
  const [draft, setDraft] = useState<KeyDraft>(EMPTY_DRAFT);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, KeyPatch>>({});
  const [agentOptions, setAgentOptions] = useState<{ value: string; label: string }[]>([]);
  const [toolOptions, setToolOptions] = useState<{ value: string; label: string }[]>([]);
  const [skillOptions, setSkillOptions] = useState<{ value: string; label: string }[]>([]);
  const { dirty: keyDirty, captureBaseline: captureKey } = useBaselineDirty(draft, true);
  const [pageSearch, setPageSearch] = useState("");

  const filteredKeys = useMemo(() => {
    if (!pageSearch.trim()) {
      return keys;
    }
    return keys.filter((key) =>
      matchesPageSearch(pageSearch, [
        key.name,
        key.id,
        ...key.scopes,
        ...(key.agent_slugs ?? []),
        ...(key.tool_slugs ?? []),
        ...(key.skill_slugs ?? []),
      ]),
    );
  }, [keys, pageSearch]);

  useAssistForm(
    "service-keys",
    {
      page_search: pageSearch,
      keys: keys.map((key) => ({
        id: key.id,
        name: key.name,
        scopes: key.scopes,
      })),
    },
    (fields) => {
      const { page_search: _p, ...rest } = fields;
      return Object.keys(rest).length === 0 ? null : t("assist.unexpectedFields");
    },
    (query) => {
      setPageSearch(query);
      return null;
    },
  );

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<ServiceKey[] | { items: ServiceKey[] }>("/api/admin/service-keys");
      const items = asItems(data);
      setKeys(items);
      setDrafts(
        Object.fromEntries(items.map((key) => [key.id, patchFromKey(key)])),
      );
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setKeys([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadCatalogOptions = useCallback(async () => {
    try {
      const [agents, tools, skills] = await Promise.all([
        apiFetch<AgentList>(`/v1/agents${buildQuery({ scope: "shared", limit: 200 })}`),
        apiFetch<ToolSpec[]>("/v1/tools"),
        apiFetch<SkillList>("/v1/skills"),
      ]);
      setAgentOptions(
        ((agents.items ?? []) as Agent[])
          .filter((agent) => agent.status === "published" && agent.visibility === "shared")
          .map((agent) => ({ value: agent.slug, label: `${agent.name} (${agent.slug})` })),
      );
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
      setAgentOptions([]);
      setToolOptions([]);
      setSkillOptions([]);
    }
  }, []);

  useEffect(() => {
    if (me.user.is_superadmin) {
      void load();
      void loadCatalogOptions();
    } else {
      setLoading(false);
    }
  }, [load, loadCatalogOptions, me.user.is_superadmin]);

  const persistKey = async () => {
    const created = await apiFetch<ServiceKeyCreated>("/api/admin/service-keys", {
      method: "POST",
      body: jsonBody({
        name: draft.name.trim(),
        scopes: draft.scopes,
        agent_slugs: draft.agent_slugs,
        tool_slugs: draft.tool_slugs,
        skill_slugs: draft.skill_slugs,
      }),
    });
    setCreatedKey(created.key);
    setDraft(EMPTY_DRAFT);
    captureKey(EMPTY_DRAFT);
    await load();
  };

  const handleCreate = async () => {
    setBusy("create");
    setError(null);
    setCreatedKey(null);
    try {
      await persistKey();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  useUnsavedGuard(
    "service-key-form",
    Boolean(me.user.is_superadmin) && keyDirty,
    async () => {
      if (!draft.name.trim() || draft.scopes.length === 0) {
        throw new Error(t("serviceKeys.nameAndScopeRequired"));
      }
      setError(null);
      try {
        await persistKey();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        throw err;
      }
    },
  );

  const updateKeyDraft = (id: string, patch: Partial<KeyPatch>) => {
    setDrafts((prev) => ({
      ...prev,
      [id]: { ...(prev[id] ?? { scopes: [], agent_slugs: [], tool_slugs: [], skill_slugs: [] }), ...patch },
    }));
  };

  const keyHasChanges = (key: ServiceKey): boolean => {
    const current = drafts[key.id] ?? patchFromKey(key);
    return (
      !scopesEqual(current.scopes, key.scopes) ||
      !scopesEqual(current.agent_slugs, key.agent_slugs ?? []) ||
      !scopesEqual(current.tool_slugs, key.tool_slugs ?? []) ||
      !scopesEqual(current.skill_slugs, key.skill_slugs ?? [])
    );
  };

  const handleUpdate = async (key: ServiceKey) => {
    const current = drafts[key.id] ?? patchFromKey(key);
    if (current.scopes.length === 0) {
      setError(t("serviceKeys.nameAndScopeRequired"));
      return;
    }
    setBusy(`update-${key.id}`);
    setError(null);
    try {
      await apiFetch<ServiceKey>(`/api/admin/service-keys/${encodeURIComponent(key.id)}`, {
        method: "PATCH",
        body: jsonBody(current),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const handleRevoke = async (id: string) => {
    setBusy(id);
    setError(null);
    try {
      await apiFetch<unknown>(`/api/admin/service-keys/${encodeURIComponent(id)}/revoke`, {
        method: "POST",
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const handleRestore = async (id: string) => {
    setBusy(`restore-${id}`);
    setError(null);
    try {
      await apiFetch<ServiceKey>(`/api/admin/service-keys/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: jsonBody({ enabled: true }),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const handleDelete = async (key: ServiceKey) => {
    const ok = window.confirm(
      `${t("serviceKeys.deleteTitle", { name: key.name })}\n\n${t("serviceKeys.deleteBody")}`,
    );
    if (!ok) return;
    setBusy(`delete-${key.id}`);
    setError(null);
    try {
      await apiFetch<unknown>(`/api/admin/service-keys/${encodeURIComponent(key.id)}`, {
        method: "DELETE",
      });
      notifySuccess(t("serviceKeys.deleted", { name: key.name }));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  if (!me.user.is_superadmin) {
    return (
      <Alert color="yellow" title={t("serviceKeys.forbiddenTitle")}>
        {t("serviceKeys.forbiddenBody")}
      </Alert>
    );
  }

  return (
    <Stack gap="md">
      <PageHeader title={t("serviceKeys.title")}>
        <PageSearch value={pageSearch} onChange={setPageSearch} />
      </PageHeader>

      {error ? (
        <Alert color="red" title={t("common.error")}>
          {error}
        </Alert>
      ) : null}

      <Card withBorder>
        <Stack gap="md">
          <Group justify="space-between" align="flex-start" wrap="nowrap">
            <Box>
              <Text fw={600}>{t("serviceKeys.newKey")}</Text>
              <Text size="xs" c="dimmed" mt={2}>
                {t("serviceKeys.allowlistHint")}
              </Text>
            </Box>
            <Button
              onClick={() => void handleCreate()}
              loading={busy === "create"}
              disabled={!draft.name.trim() || draft.scopes.length === 0}
            >
              {t("serviceKeys.createKey")}
            </Button>
          </Group>
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
            <TextInput
              {...NO_AUTOFILL}
              label={t("common.name")}
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.currentTarget.value })}
              required
            />
            <Stack gap={6}>
              <MultiSelect
                label={t("serviceKeys.scopes")}
                description={t("serviceKeys.scopesHint")}
                data={SERVICE_KEY_SCOPES.map((scope) => ({
                  value: scope,
                  // Short pill text so chips sit in a row; full label in dropdown.
                  label: scope,
                }))}
                value={draft.scopes}
                onChange={(scopes) => setDraft({ ...draft, scopes })}
                size="sm"
                styles={{
                  pillsList: { flexWrap: "wrap", gap: 4, rowGap: 4 },
                  pill: { maxWidth: "none" },
                }}
                renderOption={(item: ComboboxLikeRenderOptionInput<ComboboxItem>) => (
                  <Stack gap={2} style={{ flex: 1 }}>
                    <Text size="sm">
                      {t(`serviceKeys.scopeLabels.${scopeI18nKey(item.option.value)}`)}{" "}
                      <Text span size="xs" c="dimmed">
                        ({item.option.value})
                      </Text>
                    </Text>
                    <Text size="xs" c="dimmed">
                      {t(`serviceKeys.scopeHints.${scopeI18nKey(item.option.value)}`)}
                    </Text>
                  </Stack>
                )}
              />
              <Group gap={4} wrap="wrap">
                <Text size="xs" c="dimmed">
                  {t("serviceKeys.scopePresets.label")}
                </Text>
                {SCOPE_PRESET_ORDER.map((id) => {
                  const selected = activeScopePreset(draft.scopes) === id;
                  return (
                    <Tooltip
                      key={id}
                      label={t(`serviceKeys.scopePresets.${id}Hint`)}
                      multiline
                      w={280}
                      withArrow
                    >
                      <Button
                        size="compact-xs"
                        variant={selected ? "filled" : "default"}
                        onClick={() =>
                          setDraft({
                            ...draft,
                            scopes: [...SERVICE_KEY_SCOPE_PRESETS[id]],
                          })
                        }
                      >
                        {t(`serviceKeys.scopePresets.${id}`)}
                      </Button>
                    </Tooltip>
                  );
                })}
              </Group>
            </Stack>
          </SimpleGrid>
          <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
            <AllowlistMultiSelect
              size="xs"
              label={t("serviceKeys.agentsAllowlist")}
              data={agentOptions}
              value={draft.agent_slugs}
              onChange={(agent_slugs) => setDraft({ ...draft, agent_slugs })}
            />
            <AllowlistMultiSelect
              size="xs"
              label={t("serviceKeys.toolsAllowlist")}
              data={toolOptions}
              value={draft.tool_slugs}
              onChange={(tool_slugs) => setDraft({ ...draft, tool_slugs })}
            />
            <AllowlistMultiSelect
              size="xs"
              label={t("serviceKeys.skillsAllowlist")}
              data={skillOptions}
              value={draft.skill_slugs}
              onChange={(skill_slugs) => setDraft({ ...draft, skill_slugs })}
            />
          </SimpleGrid>

          {createdKey ? (
            <Stack gap="xs">
              <Alert color="green" variant="light">
                {t("serviceKeys.keyOnce")}
              </Alert>
              <Code block style={{ whiteSpace: "pre-wrap" }}>
                {createdKey}
              </Code>
              <Group>
                <Button size="xs" variant="default" onClick={() => setCreatedKey(null)}>
                  {t("common.hide")}
                </Button>
              </Group>
            </Stack>
          ) : null}
        </Stack>
      </Card>

      <Card withBorder padding={0}>
        {loading ? (
          <Group justify="center" p="xl">
            <Loader size="sm" />
          </Group>
        ) : keys.length === 0 ? (
          <Text p="xl" c="dimmed" size="sm">
            {t("serviceKeys.empty")}
          </Text>
        ) : filteredKeys.length === 0 ? (
          <Text p="xl" c="dimmed" size="sm">
            {t("common.emptyPageFilter")}
          </Text>
        ) : (
          <Table.ScrollContainer minWidth={1040}>
          <Table
            striped
            highlightOnHover
            withTableBorder
            verticalSpacing="xs"
            style={{ tableLayout: "fixed", width: "100%" }}
          >
            <Table.Thead>
              <Table.Tr>
                <Table.Th style={{ width: "12%" }}>{t("serviceKeys.columns.name")}</Table.Th>
                <Table.Th style={{ width: "20%" }}>{t("serviceKeys.columns.scopes")}</Table.Th>
                <Table.Th style={{ width: "34%" }}>{t("serviceKeys.columns.catalog")}</Table.Th>
                <Table.Th style={{ width: "10%" }}>{t("serviceKeys.columns.status")}</Table.Th>
                <Table.Th style={{ width: "8%" }}>{t("serviceKeys.columns.created")}</Table.Th>
                <Table.Th style={{ width: "8%" }}>{t("serviceKeys.columns.used")}</Table.Th>
                <Table.Th style={{ width: "8%" }} />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {filteredKeys.map((key) => {
                const current = drafts[key.id] ?? patchFromKey(key);
                const changed = keyHasChanges(key);
                return (
                <Table.Tr key={key.id}>
                  <Table.Td>
                    <Text size="sm" fw={500} lineClamp={2}>
                      {key.name}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <MultiSelect
                      size="xs"
                      data={SERVICE_KEY_SCOPES.map((scope) => ({
                        value: scope,
                        label: scope,
                      }))}
                      value={current.scopes}
                      onChange={(scopes) => updateKeyDraft(key.id, { scopes })}
                      disabled={!key.enabled}
                      searchable
                      clearable
                      renderOption={(item: ComboboxLikeRenderOptionInput<ComboboxItem>) => (
                        <Stack gap={2} style={{ flex: 1 }}>
                          <Text size="sm">
                            {t(`serviceKeys.scopeLabels.${scopeI18nKey(item.option.value)}`)}{" "}
                            <Text span size="xs" c="dimmed">
                              ({item.option.value})
                            </Text>
                          </Text>
                          <Text size="xs" c="dimmed">
                            {t(`serviceKeys.scopeHints.${scopeI18nKey(item.option.value)}`)}
                          </Text>
                        </Stack>
                      )}
                    />
                  </Table.Td>
                  <Table.Td>
                    <Stack gap={4}>
                      <AllowlistMultiSelect
                        size="xs"
                        label={t("serviceKeys.agentsAllowlist")}
                        data={agentOptions}
                        value={current.agent_slugs}
                        onChange={(agent_slugs) => updateKeyDraft(key.id, { agent_slugs })}
                        disabled={!key.enabled}
                      />
                      <AllowlistMultiSelect
                        size="xs"
                        label={t("serviceKeys.toolsAllowlist")}
                        data={toolOptions}
                        value={current.tool_slugs}
                        onChange={(tool_slugs) => updateKeyDraft(key.id, { tool_slugs })}
                        disabled={!key.enabled}
                      />
                      <AllowlistMultiSelect
                        size="xs"
                        label={t("serviceKeys.skillsAllowlist")}
                        data={skillOptions}
                        value={current.skill_slugs}
                        onChange={(skill_slugs) => updateKeyDraft(key.id, { skill_slugs })}
                        disabled={!key.enabled}
                      />
                    </Stack>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={8} wrap="nowrap">
                      <Switch
                        size="sm"
                        checked={key.enabled}
                        disabled={busy === key.id || busy === `restore-${key.id}`}
                        onChange={(event) =>
                          event.currentTarget.checked
                            ? void handleRestore(key.id)
                            : void handleRevoke(key.id)
                        }
                        aria-label={
                          key.enabled
                            ? t("serviceKeys.revoke")
                            : t("serviceKeys.restore")
                        }
                      />
                      <Text size="xs" c={key.enabled ? "green" : "red"}>
                        {key.enabled ? t("serviceKeys.active") : t("serviceKeys.revoked")}
                      </Text>
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" style={{ whiteSpace: "nowrap" }}>
                      {formatDate(key.created_at)}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" style={{ whiteSpace: "nowrap" }}>
                      {formatDate(key.last_used_at)}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4} wrap="nowrap">
                      {changed && key.enabled ? (
                        <Tooltip label={t("serviceKeys.updateChanges")}>
                          <ActionIcon
                            variant="light"
                            color="blue"
                            loading={busy === `update-${key.id}`}
                            onClick={() => void handleUpdate(key)}
                            aria-label={t("serviceKeys.updateChanges")}
                          >
                            <CheckIcon />
                          </ActionIcon>
                        </Tooltip>
                      ) : null}
                      <Tooltip label={t("serviceKeys.delete")}>
                        <ActionIcon
                          variant="light"
                          color="red"
                          loading={busy === `delete-${key.id}`}
                          onClick={() => void handleDelete(key)}
                          aria-label={t("serviceKeys.delete")}
                        >
                          <TrashIcon />
                        </ActionIcon>
                      </Tooltip>
                    </Group>
                  </Table.Td>
                </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
          </Table.ScrollContainer>
        )}
      </Card>
    </Stack>
  );
}
