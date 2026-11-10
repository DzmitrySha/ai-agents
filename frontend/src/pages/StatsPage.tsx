import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Alert,
  Badge,
  Card,
  Center,
  Chip,
  Group,
  Loader,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Table,
  Text,
} from "@mantine/core";
import { BarChart, LineChart } from "@mantine/charts";
import { useTranslation } from "react-i18next";
import { apiFetch } from "../api";
import { PageHeader, PageSearch } from "../components/PageHeader";
import { readStored, writeStored } from "../components/useStoredState";
import { useAssistForm } from "../assist";
import { matchesPageSearch } from "../pageSearch";
import type { RunsDailyPoint, StatsOverview } from "../types";

const WINDOW_VALUES = ["7", "14", "30"] as const;

const RUN_STATUS_VALUES = ["succeeded", "failed", "cancelled"] as const;

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function shortDate(value: string): string {
  const [, month, day] = value.split("-");
  return `${day}.${month}`;
}

export function StatsPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialDays = searchParams.get("days");
  const storedDays = readStored<string>("ai-agents.stats.days", "14");
  const [days, setDays] = useState(
    initialDays && WINDOW_VALUES.some((window) => window === initialDays)
      ? initialDays
      : WINDOW_VALUES.some((window) => window === storedDays)
        ? storedDays
        : "14",
  );
  const [statuses, setStatuses] = useState<string[]>(() =>
    (searchParams.get("status") ?? readStored<string[]>("ai-agents.stats.statuses", []).join(","))
      .split(",")
      .map((value) => value.trim())
      .filter((value) => RUN_STATUS_VALUES.some((status) => status === value)),
  );
  const [data, setData] = useState<StatsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pageSearch, setPageSearch] = useState("");

  const windows = useMemo(
    () => [
      { label: t("stats.windows.d7"), value: "7" },
      { label: t("stats.windows.d14"), value: "14" },
      { label: t("stats.windows.d30"), value: "30" },
    ],
    [t],
  );

  const runStatuses = useMemo(
    () =>
      [
        { value: "succeeded", label: t("stats.statusSucceeded"), color: "teal" },
        { value: "failed", label: t("stats.statusFailed"), color: "red" },
        { value: "cancelled", label: t("stats.statusCancelled"), color: "gray" },
      ] as const,
    [t],
  );

  const formatMs = (value: number | null | undefined): string => {
    if (value === null || value === undefined) {
      return t("common.emptyDash");
    }
    return value >= 1000
      ? t("stats.sec", { value: (value / 1000).toFixed(1) })
      : t("stats.ms", { value });
  };

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    apiFetch<StatsOverview>(`/v1/stats/overview?days=${days}`)
      .then((value) => {
        if (alive) {
          setData(value);
        }
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
  }, [days]);

  // Фильтры в URL, чтобы обзором можно было поделиться ссылкой.
  useEffect(() => {
    writeStored("ai-agents.stats.days", days);
    writeStored("ai-agents.stats.statuses", statuses);
    const next = new URLSearchParams();
    if (days !== "14") {
      next.set("days", days);
    }
    if (statuses.length > 0) {
      next.set("status", statuses.join(","));
    }
    setSearchParams(next, { replace: true });
  }, [days, statuses, setSearchParams]);

  const runsDaily = (data?.runs_daily ?? []).map((point) => ({
    ...point,
    date: shortDate(point.date),
  }));

  const runSeries = useMemo(
    () =>
      [
        { name: "succeeded", label: t("stats.statusSucceeded"), color: "teal.6" },
        { name: "failed", label: t("stats.statusFailed"), color: "red.6" },
        { name: "cancelled", label: t("stats.statusCancelled"), color: "gray.5" },
      ].filter((series) => statuses.length === 0 || statuses.includes(series.name)),
    [statuses, t],
  );

  const filteredRuns = useMemo(() => {
    const keys = statuses.length ? statuses : [...RUN_STATUS_VALUES];
    const valueOf = (point: RunsDailyPoint, key: string): number => {
      if (key === "succeeded") {
        return point.succeeded;
      }
      if (key === "failed") {
        return point.failed;
      }
      if (key === "cancelled") {
        return point.cancelled;
      }
      return point.other;
    };
    return (data?.runs_daily ?? []).reduce(
      (total, point) => total + keys.reduce((sum, key) => sum + valueOf(point, key), 0),
      0,
    );
  }, [data, statuses]);
  const toolDaily = (data?.tools_daily ?? []).map((point) => ({
    ...point,
    date: shortDate(point.date),
  }));
  const apiDaily = (data?.api_daily ?? []).map((point) => ({
    ...point,
    date: shortDate(point.date),
  }));
  const topToolsRaw = useMemo(() => data?.top_tools ?? [], [data]);
  const filteredTopToolsRaw = useMemo(() => {
    if (!pageSearch.trim()) {
      return topToolsRaw;
    }
    return topToolsRaw.filter((tool) =>
      matchesPageSearch(pageSearch, [tool.slug, tool.calls]),
    );
  }, [topToolsRaw, pageSearch]);

  const topAgentsRaw = useMemo(() => data?.top_agents ?? [], [data]);
  const filteredTopAgents = useMemo(() => {
    if (!pageSearch.trim()) {
      return topAgentsRaw;
    }
    return topAgentsRaw.filter((agent) =>
      matchesPageSearch(pageSearch, [
        agent.slug,
        agent.runs,
        agent.succeeded,
        agent.failed,
        agent.avg_duration_ms,
        agent.tokens,
      ]),
    );
  }, [topAgentsRaw, pageSearch]);

  const topEndpointsRaw = useMemo(() => data?.top_endpoints ?? [], [data]);
  const filteredTopEndpoints = useMemo(() => {
    if (!pageSearch.trim()) {
      return topEndpointsRaw;
    }
    return topEndpointsRaw.filter((endpoint) =>
      matchesPageSearch(pageSearch, [
        endpoint.method,
        endpoint.path,
        endpoint.calls,
        endpoint.errors,
        endpoint.p95_ms,
      ]),
    );
  }, [topEndpointsRaw, pageSearch]);

  const topTools = filteredTopToolsRaw.map((tool) => ({
    name: tool.slug,
    calls: tool.calls,
  }));

  useAssistForm(
    "general",
    {
      page_search: pageSearch,
      top_agents: (data?.top_agents ?? []).map((a) => ({ slug: a.slug, runs: a.runs, tokens: a.tokens })),
      top_endpoints: (data?.top_endpoints ?? []).map((e) => ({
        method: e.method,
        path: e.path,
      })),
      top_tools: (data?.top_tools ?? []).map((tool) => ({ slug: tool.slug, calls: tool.calls })),
    },
    (fields) => {
      const { page_search: _p, ...rest } = fields;
      if (Object.keys(rest).length === 0) {
        return null;
      }
      return t("assist.unexpectedFields");
    },
    (query) => {
      setPageSearch(query);
      return null;
    },
  );

  return (
    <Stack gap="md">
      <PageHeader title={t("stats.title")}>
        <PageSearch value={pageSearch} onChange={setPageSearch} />
        {data ? (
          <Badge variant="light" color="gray">
            {t("stats.since", { date: shortDate(data.since.slice(0, 10)) })}
          </Badge>
        ) : null}
        {data ? (
          <Badge variant="light" color={data.queued_runs > 0 ? "blue" : "gray"}>
            {t("stats.queue", { count: data.queued_runs })}
          </Badge>
        ) : null}
        {data?.oldest_queued_seconds !== null && data?.oldest_queued_seconds !== undefined ? (
          <Badge variant="light" color="orange">
            {t("stats.oldestQueued", { value: data.oldest_queued_seconds })}
          </Badge>
        ) : null}
        <SegmentedControl data={windows} value={days} onChange={setDays} />
      </PageHeader>

      {error ? (
        <Alert color="red" title={t("common.error")}>
          {error}
        </Alert>
      ) : null}

      {loading && !data ? (
        <Center py="xl">
          <Loader />
        </Center>
      ) : data ? (
        <>
          <SimpleGrid cols={{ base: 2, sm: 3, lg: 7 }} spacing="md">
            <Card withBorder>
              <Text size="xs" c="dimmed">
                {t("stats.cards.runs")}
              </Text>
              <Text fw={700} size="xl">
                {data.runs_total}
              </Text>
            </Card>
            <Card withBorder>
              <Text size="xs" c="dimmed">
                {t("stats.cards.successRate")}
              </Text>
              <Text fw={700} size="xl">
                {percent(data.success_rate)}
              </Text>
            </Card>
            <Card withBorder>
              <Text size="xs" c="dimmed">
                {t("stats.cards.toolCalls")}
              </Text>
              <Text fw={700} size="xl">
                {data.tools_total}
              </Text>
            </Card>
            <Card withBorder>
              <Text size="xs" c="dimmed">
                {t("stats.cards.tokens")}
              </Text>
              <Text fw={700} size="xl">
                {data.tokens_total}
              </Text>
            </Card>
            <Card withBorder>
              <Text size="xs" c="dimmed">
                {t("stats.cards.apiRequests")}
              </Text>
              <Text fw={700} size="xl">
                {data.api_total}
              </Text>
            </Card>
            <Card withBorder>
              <Text size="xs" c="dimmed">
                {t("stats.cards.apiErrors")}
              </Text>
              <Text fw={700} size="xl" c={data.api_errors > 0 ? "red.6" : undefined}>
                {data.api_errors}
              </Text>
            </Card>
            <Card withBorder>
              <Text size="xs" c="dimmed">
                {t("stats.cards.apiP95")}
              </Text>
              <Text fw={700} size="xl">
                {formatMs(data.api_latency.p95_ms)}
              </Text>
            </Card>
          </SimpleGrid>

          <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
            <Card withBorder>
              <Stack gap="xs">
                <Group justify="space-between" align="center">
                  <Text fw={600}>{t("stats.runsDaily")}</Text>
                  <Badge variant="light">{t("stats.forPeriod", { count: filteredRuns })}</Badge>
                </Group>
                <Chip.Group multiple value={statuses} onChange={setStatuses}>
                  <Group gap="xs">
                    {runStatuses.map((status) => (
                      <Chip key={status.value} value={status.value} size="xs" variant="light">
                        {status.label}
                      </Chip>
                    ))}
                  </Group>
                </Chip.Group>
                <BarChart
                  h={240}
                  data={runsDaily}
                  dataKey="date"
                  type="stacked"
                  series={runSeries}
                  withLegend
                  legendProps={{ verticalAlign: "bottom" }}
                />
              </Stack>
            </Card>

            <Card withBorder>
              <Stack gap="xs">
                <Text fw={600}>{t("stats.apiSeries")}</Text>
                <LineChart
                  h={240}
                  data={apiDaily}
                  dataKey="date"
                  curveType="natural"
                  series={[
                    { name: "calls", label: t("stats.seriesRequests"), color: "blue.6" },
                    { name: "errors", label: t("stats.seriesErrors"), color: "red.6" },
                  ]}
                  withLegend
                  legendProps={{ verticalAlign: "bottom" }}
                />
              </Stack>
            </Card>

            <Card withBorder>
              <Stack gap="xs">
                <Text fw={600}>{t("stats.toolsDaily")}</Text>
                <BarChart
                  h={220}
                  data={toolDaily}
                  dataKey="date"
                  series={[{ name: "calls", label: t("stats.seriesCalls"), color: "violet.6" }]}
                />
              </Stack>
            </Card>

            <Card withBorder>
              <Stack gap="xs">
                <Text fw={600}>{t("stats.topTools")}</Text>
                {topToolsRaw.length === 0 ? (
                  <Text size="sm" c="dimmed">
                    {t("stats.noToolCalls")}
                  </Text>
                ) : filteredTopToolsRaw.length === 0 ? (
                  <Text size="sm" c="dimmed">
                    {t("common.emptyPageFilter")}
                  </Text>
                ) : (
                  <BarChart
                    h={220}
                    data={topTools}
                    dataKey="name"
                    orientation="vertical"
                    series={[{ name: "calls", label: t("stats.seriesCalls"), color: "violet.6" }]}
                    barProps={{ radius: 4 }}
                  />
                )}
              </Stack>
            </Card>
          </SimpleGrid>

          <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
            <Card withBorder>
              <Stack gap="xs">
                <Text fw={600}>{t("stats.agents")}</Text>
                {topAgentsRaw.length === 0 ? (
                  <Text size="sm" c="dimmed">
                    {t("stats.noAgentRuns")}
                  </Text>
                ) : filteredTopAgents.length === 0 ? (
                  <Text size="sm" c="dimmed">
                    {t("common.emptyPageFilter")}
                  </Text>
                ) : (
                  <Table.ScrollContainer minWidth={560}>
                    <Table striped highlightOnHover>
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>{t("stats.agentColumns.agent")}</Table.Th>
                          <Table.Th>{t("stats.agentColumns.runs")}</Table.Th>
                          <Table.Th>{t("stats.agentColumns.succeeded")}</Table.Th>
                          <Table.Th>{t("stats.agentColumns.failed")}</Table.Th>
                          <Table.Th>{t("stats.agentColumns.tokens")}</Table.Th>
                          <Table.Th>{t("stats.agentColumns.avgTime")}</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {filteredTopAgents.map((agent) => (
                          <Table.Tr key={agent.slug}>
                            <Table.Td>{agent.slug}</Table.Td>
                            <Table.Td>{agent.runs}</Table.Td>
                            <Table.Td>{agent.succeeded}</Table.Td>
                            <Table.Td>{agent.failed}</Table.Td>
                            <Table.Td>{agent.tokens}</Table.Td>
                            <Table.Td>{formatMs(agent.avg_duration_ms)}</Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Table.ScrollContainer>
                )}
              </Stack>
            </Card>

            <Card withBorder>
              <Stack gap="xs">
                <Text fw={600}>{t("stats.topEndpoints")}</Text>
                {topEndpointsRaw.length === 0 ? (
                  <Text size="sm" c="dimmed">
                    {t("stats.noApiRequests")}
                  </Text>
                ) : filteredTopEndpoints.length === 0 ? (
                  <Text size="sm" c="dimmed">
                    {t("common.emptyPageFilter")}
                  </Text>
                ) : (
                  <Table.ScrollContainer minWidth={520}>
                    <Table striped highlightOnHover>
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>{t("stats.endpointColumns.method")}</Table.Th>
                          <Table.Th>{t("stats.endpointColumns.path")}</Table.Th>
                          <Table.Th>{t("stats.endpointColumns.calls")}</Table.Th>
                          <Table.Th>{t("stats.endpointColumns.errors")}</Table.Th>
                          <Table.Th>{t("stats.endpointColumns.p95")}</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {filteredTopEndpoints.map((endpoint) => (
                          <Table.Tr key={`${endpoint.method} ${endpoint.path}`}>
                            <Table.Td>{endpoint.method}</Table.Td>
                            <Table.Td>{endpoint.path}</Table.Td>
                            <Table.Td>{endpoint.calls}</Table.Td>
                            <Table.Td>{endpoint.errors}</Table.Td>
                            <Table.Td>{formatMs(endpoint.p95_ms)}</Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Table.ScrollContainer>
                )}
              </Stack>
            </Card>
          </SimpleGrid>
        </>
      ) : null}
    </Stack>
  );
}
