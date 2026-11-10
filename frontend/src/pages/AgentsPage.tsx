import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Alert,
  Badge,
  Button,
  Card,
  Code,
  Group,
  Loader,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Table,
  Text,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { apiFetch, buildQuery } from "../api";
import { roleOf, useSession } from "../components/AppLayout";
import {
  IconAction,
  IconLink,
  PageHeader,
  PageSearch,
  readViewMode,
  saveViewMode,
  ViewToggle,
  type ViewMode,
} from "../components/PageHeader";
import { PlusIcon } from "../components/icons";
import { useStoredState } from "../components/useStoredState";
import { formatDate } from "../format";
import { useAssistForm } from "../assist";
import type { Agent, AgentList, AgentScope, AgentStatus, AgentVisibility } from "../types";
import { matchesPageSearch } from "../pageSearch";
import { ASSIST_AGENT_FIELDS_KEY } from "./agents/agentForm";

const STATUS_COLORS: Record<AgentStatus, string> = {
  draft: "gray",
  published: "green",
  archived: "red",
};

function StaleBadges({ agent }: { agent: Agent }) {
  const { t } = useTranslation();
  if (!agent.skills_stale && !agent.tools_stale) return null;
  return (
    <Group gap={4} wrap="wrap">
      {agent.skills_stale ? (
        <Badge size="sm" variant="light" color="orange" title={t("agents.staleSkillsTitle")}>
          {t("agents.staleSkills")}
        </Badge>
      ) : null}
      {agent.tools_stale ? (
        <Badge size="sm" variant="light" color="grape" title={t("agents.staleToolsTitle")}>
          {t("agents.staleTools")}
        </Badge>
      ) : null}
    </Group>
  );
}

function statusLabel(status: AgentStatus, t: (key: string) => string): string {
  if (status === "draft" || status === "published" || status === "archived") {
    return t(`common.${status}`);
  }
  return status;
}

function visibilityLabel(visibility: AgentVisibility, t: (key: string) => string): string {
  if (visibility === "private" || visibility === "shared") {
    return t(`agents.visibility.${visibility}`);
  }
  return visibility;
}

export function AgentsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const me = useSession();
  const isReader = roleOf(me) === "user";
  const canWrite = !isReader;
  const isSuperadmin = me.user.is_superadmin;
  // Пользователь видит только опубликованные общие агенты — чужих "своих" у него нет.
  const scopeOptions: { label: string; value: AgentScope }[] = [
    ...(isSuperadmin ? [{ label: t("agents.scopes.all"), value: "all" as AgentScope }] : []),
    { label: t("agents.scopes.shared"), value: "shared" },
    ...(isReader
      ? []
      : [
          { label: t("agents.scopes.owned"), value: "owned" as AgentScope },
          { label: t("agents.scopes.archived"), value: "archived" as AgentScope },
        ]),
  ];
  const defaultScope: AgentScope = isSuperadmin ? "all" : "shared";
  const [storedScope, setScope] = useStoredState<AgentScope>("ai-agents.scope.agents", defaultScope);
  const scope = scopeOptions.some((option) => option.value === storedScope)
    ? storedScope
    : defaultScope;
  const isArchive = scope === "archived";
  const [view, setView] = useState<ViewMode>(() => readViewMode("agents"));
  const [staleOnly, setStaleOnly] = useState(false);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [pageSearch, setPageSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const filteredAgents = useMemo(() => {
    if (!pageSearch.trim()) {
      return agents;
    }
    return agents.filter((agent) =>
      matchesPageSearch(pageSearch, [
        agent.name,
        agent.slug,
        agent.description,
        agent.status,
        agent.visibility,
        ...(agent.tools ?? []),
        ...(agent.skills ?? []),
      ]),
    );
  }, [agents, pageSearch]);

  // Список агентов тоже регистрирует форму: advice видит каталог страницы,
  // form → fields в sessionStorage и переход в /agents/new.
  useAssistForm(
    "agent",
    {
      page_search: pageSearch,
      taken_slugs: agents.map((agent) => agent.slug),
      agents: agents.map((agent) => ({
        slug: agent.slug,
        name: agent.name,
        description: agent.description,
        status: agent.status,
        visibility: agent.visibility,
      })),
    },
    (fields) => {
      const { page_search: _p, ...rest } = fields;
      if (Object.keys(rest).length === 0) {
        return null;
      }
      if (!canWrite) {
        return t("agents.assistNeedWrite");
      }
      try {
        sessionStorage.setItem(ASSIST_AGENT_FIELDS_KEY, JSON.stringify(rest));
      } catch {
        return t("agents.assistDraftFailed");
      }
      navigate("/agents/new");
      return null;
    },
    (query) => {
      setPageSearch(query);
      return null;
    },
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<AgentList>(
        `/v1/agents${buildQuery({
          scope,
          limit: 200,
          ...(staleOnly ? { stale: "any" } : {}),
        })}`,
      );
      const items = [...(data.items ?? [])].sort((a, b) => {
        const score = (agent: Agent) =>
          Number(Boolean(agent.skills_stale)) + Number(Boolean(agent.tools_stale));
        return score(b) - score(a);
      });
      setAgents(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setAgents([]);
    } finally {
      setLoading(false);
    }
  }, [scope, staleOnly]);

  useEffect(() => {
    void load();
  }, [load]);

  const changeView = (value: ViewMode) => {
    setView(value);
    saveViewMode("agents", value);
  };

  const runsLink = (agent: Agent) => `/runs?agent_id=${encodeURIComponent(agent.slug)}`;
  const editorLink = (agent: Agent) => `/agents/${encodeURIComponent(agent.slug)}`;

  return (
    <Stack gap="md">
      <PageHeader title={t("agents.title")} count={filteredAgents.length}>
        <PageSearch value={pageSearch} onChange={setPageSearch} />
        <ViewToggle value={view} onChange={changeView} />
        <IconAction
          kind="refresh"
          label={t("common.refresh")}
          onClick={() => void load()}
          loading={loading}
        />
        {isReader ? null : (
          <Button component={Link} to="/agents/new" leftSection={<PlusIcon />}>
            {t("agents.add")}
          </Button>
        )}
      </PageHeader>

      <Group justify="space-between" align="center" wrap="wrap">
        <SegmentedControl
          value={scope}
          onChange={(value) => setScope(value as AgentScope)}
          data={scopeOptions}
        />
        {isArchive ? null : (
          <SegmentedControl
            value={staleOnly ? "stale" : "all"}
            onChange={(value) => setStaleOnly(value === "stale")}
            data={[
              { label: t("agents.staleFilter.all"), value: "all" },
              { label: t("agents.staleFilter.stale"), value: "stale" },
            ]}
          />
        )}
      </Group>

      {error ? (
        <Alert color="red" title={t("common.loadError")}>
          {error}
        </Alert>
      ) : null}

      {loading ? (
        <Group justify="center" p="xl">
          <Loader size="sm" />
        </Group>
      ) : agents.length === 0 ? (
        <Text p="xl" c="dimmed" size="sm">
          {staleOnly
            ? t("agents.emptyStale")
            : isArchive
              ? t("agents.emptyArchive")
              : t("agents.empty")}
        </Text>
      ) : filteredAgents.length === 0 ? (
        <Text p="xl" c="dimmed" size="sm">
          {t("agents.emptyFilter")}
        </Text>
      ) : view === "table" ? (
        <Card withBorder padding={0}>
          <Table.ScrollContainer minWidth={860}>
            <Table striped highlightOnHover withTableBorder verticalSpacing="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("agents.columns.name")}</Table.Th>
                  <Table.Th>{t("agents.columns.tools")}</Table.Th>
                  <Table.Th>{t("agents.columns.visibility")}</Table.Th>
                  <Table.Th>{t("agents.columns.status")}</Table.Th>
                  <Table.Th>{t("agents.columns.updated")}</Table.Th>
                  <Table.Th w={110} />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {filteredAgents.map((agent) => (
                  <Table.Tr key={agent.id}>
                    <Table.Td>
                      <Text component={Link} to={editorLink(agent)} size="sm" fw={500}>
                        {agent.name}
                      </Text>
                      <Code style={{ fontSize: 11 }}>{agent.slug}</Code>
                    </Table.Td>
                    <Table.Td>
                      <Group gap={4}>
                        {agent.tools.length === 0 ? (
                          <Text size="xs" c="dimmed">
                            {t("common.emptyDash")}
                          </Text>
                        ) : (
                          agent.tools.slice(0, 3).map((tool) => (
                            <Badge key={tool} size="sm" variant="light" color="blue">
                              {tool}
                            </Badge>
                          ))
                        )}
                        {agent.tools.length > 3 ? (
                          <Badge size="sm" variant="light" color="gray">
                            +{agent.tools.length - 3}
                          </Badge>
                        ) : null}
                      </Group>
                    </Table.Td>
                    <Table.Td>
                      <Badge size="sm" variant="outline">
                        {visibilityLabel(agent.visibility, t)}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Group gap={4} wrap="wrap">
                        <Badge size="sm" color={STATUS_COLORS[agent.status] ?? "gray"}>
                          {statusLabel(agent.status, t)}
                        </Badge>
                        <StaleBadges agent={agent} />
                      </Group>
                    </Table.Td>
                    <Table.Td>
                      <Text size="xs">{formatDate(agent.updated_at)}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Group gap={6} justify="flex-end" wrap="nowrap">
                        <IconLink kind="test" label={t("agents.runs")} to={runsLink(agent)} />
                        <IconLink kind="edit" label={t("common.edit")} to={editorLink(agent)} />
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, xl: 3 }} spacing="md">
          {filteredAgents.map((agent) => (
            <Card key={agent.id} withBorder>
              <Stack gap="xs" h="100%">
                <Group justify="space-between" gap="xs" wrap="nowrap" align="flex-start">
                  <Stack gap={2} style={{ minWidth: 0 }}>
                    <Text component={Link} to={editorLink(agent)} fw={600} lineClamp={1}>
                      {agent.name}
                    </Text>
                    <Code style={{ fontSize: 11 }}>{agent.slug}</Code>
                  </Stack>
                  <Stack gap={4} align="flex-end">
                    <Badge size="sm" color={STATUS_COLORS[agent.status] ?? "gray"}>
                      {statusLabel(agent.status, t)}
                    </Badge>
                    <StaleBadges agent={agent} />
                  </Stack>
                </Group>
                {agent.description ? (
                  <Text size="xs" c="dimmed" lineClamp={2}>
                    {agent.description}
                  </Text>
                ) : null}
                <Group gap={4}>
                  {agent.tools.slice(0, 3).map((tool) => (
                    <Badge key={tool} size="xs" variant="light" color="blue">
                      {tool}
                    </Badge>
                  ))}
                  {agent.tools.length > 3 ? (
                    <Badge size="xs" variant="light" color="gray">
                      +{agent.tools.length - 3}
                    </Badge>
                  ) : null}
                  {agent.tools.length === 0 ? (
                    <Text size="xs" c="dimmed">
                      {t("agents.noTools")}
                    </Text>
                  ) : null}
                </Group>
                <Group justify="space-between" mt="auto" align="center">
                  <Group gap={6}>
                    <Badge size="xs" variant="outline">
                      {visibilityLabel(agent.visibility, t)}
                    </Badge>
                    <Text size="xs" c="dimmed">
                      {formatDate(agent.updated_at)}
                    </Text>
                  </Group>
                  <Group gap={6} wrap="nowrap">
                    <IconLink kind="test" label={t("agents.runs")} to={runsLink(agent)} />
                    <IconLink kind="edit" label={t("common.edit")} to={editorLink(agent)} />
                  </Group>
                </Group>
              </Stack>
            </Card>
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
