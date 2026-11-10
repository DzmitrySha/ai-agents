import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Group,
  Loader,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { apiFetch, buildQuery } from "../api";
import { useAssistForm } from "../assist";
import { matchesPageSearch } from "../pageSearch";
import { IconAction, PageHeader } from "../components/PageHeader";
import { readStored, writeStored } from "../components/useStoredState";
import { NO_AUTOFILL } from "../formAttrs";
import { formatDate } from "../format";
import type { Run, RunList, RunStatus } from "../types";

const STATUS_COLORS: Record<RunStatus, string> = {
  queued: "gray",
  running: "blue",
  waiting_approval: "yellow",
  succeeded: "green",
  failed: "red",
  cancelled: "orange",
};

const RUN_STATUSES: RunStatus[] = [
  "queued",
  "running",
  "waiting_approval",
  "succeeded",
  "failed",
  "cancelled",
];

export function RunsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [status, setStatus] = useState<string | null>(
    searchParams.get("status") ?? readStored<string | null>("ai-agents.runs.status", null),
  );
  const [agentId, setAgentId] = useState(searchParams.get("agent_id") ?? "");
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pageSearch, setPageSearch] = useState("");
  const [selected, setSelected] = useState<string[]>([]);

  const toggleSelected = (runId: string) => {
    setSelected((prev) => {
      if (prev.includes(runId)) {
        return prev.filter((item) => item !== runId);
      }
      return prev.length >= 2 ? prev : [...prev, runId];
    });
  };

  const visibleRuns = useMemo(() => {
    if (!pageSearch.trim()) {
      return runs;
    }
    return runs.filter((run) =>
      matchesPageSearch(pageSearch, [
        run.run_id,
        run.agent_id,
        run.status,
        run.agent_version,
      ]),
    );
  }, [runs, pageSearch]);

  useAssistForm(
    "general",
    {
      page_search: pageSearch,
      runs: runs.map((run) => ({
        run_id: run.run_id,
        agent_id: run.agent_id,
        status: run.status,
      })),
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

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<RunList>(
        `/v1/runs${buildQuery({ status, agent_id: agentId.trim(), limit: 200 })}`,
      );
      setRuns(data.items ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setRuns([]);
    } finally {
      setLoading(false);
    }
  }, [status, agentId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    writeStored("ai-agents.runs.status", status);
    const next = new URLSearchParams();
    if (status) {
      next.set("status", status);
    }
    if (agentId.trim()) {
      next.set("agent_id", agentId.trim());
    }
    setSearchParams(next, { replace: true });
  }, [status, agentId, setSearchParams]);

  return (
    <Stack gap="md">
      <PageHeader title={t("runs.title")}>
        <Button
          variant="light"
          disabled={selected.length !== 2}
          onClick={() =>
            navigate(`/runs/compare?left=${selected[0]}&right=${selected[1]}`)
          }
        >
          {t("runs.compare")}
        </Button>
        <IconAction
          kind="refresh"
          label={t("common.refresh")}
          onClick={() => void load()}
          loading={loading}
        />
      </PageHeader>

      <Group align="flex-end">
        <Select
          label={t("runs.filters.status")}
          placeholder={t("runs.filters.statusAny")}
          clearable
          data={RUN_STATUSES.map((value) => ({
            value,
            label: t(`runs.statuses.${value}`),
          }))}
          value={status}
          onChange={setStatus}
          w={180}
        />
        <TextInput
          {...NO_AUTOFILL}
          label={t("runs.filters.agent")}
          placeholder={t("runs.filters.agentPlaceholder")}
          value={agentId}
          onChange={(event) => setAgentId(event.currentTarget.value)}
          w={260}
        />
        <TextInput
          {...NO_AUTOFILL}
          label={t("common.search")}
          placeholder={t("common.pageSearchPlaceholder")}
          value={pageSearch}
          onChange={(event) => setPageSearch(event.currentTarget.value)}
          w={260}
        />
      </Group>

      {error ? (
        <Alert color="red" title={t("common.loadError")}>
          {error}
        </Alert>
      ) : null}

      <Card withBorder padding={0}>
        {loading ? (
          <Group justify="center" p="xl">
            <Loader size="sm" />
          </Group>
        ) : runs.length === 0 ? (
          <Text p="xl" c="dimmed" size="sm">
            {t("runs.empty")}
          </Text>
        ) : visibleRuns.length === 0 ? (
          <Text p="xl" c="dimmed" size="sm">
            {t("common.emptyPageFilter")}
          </Text>
        ) : (
          <Table striped highlightOnHover withTableBorder verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th />
                <Table.Th>{t("runs.columns.run")}</Table.Th>
                <Table.Th>{t("runs.columns.agent")}</Table.Th>
                <Table.Th>{t("runs.columns.version")}</Table.Th>
                <Table.Th>{t("runs.columns.status")}</Table.Th>
                <Table.Th>{t("runs.columns.created")}</Table.Th>
                <Table.Th>{t("runs.columns.finished")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {visibleRuns.map((run) => (
                <Table.Tr key={run.run_id}>
                  <Table.Td>
                    <Checkbox
                      aria-label={t("runs.selectRun")}
                      checked={selected.includes(run.run_id)}
                      disabled={
                        selected.length === 2 && !selected.includes(run.run_id)
                      }
                      onChange={() => toggleSelected(run.run_id)}
                    />
                  </Table.Td>
                  <Table.Td>
                    <Link to={`/runs/${encodeURIComponent(run.run_id)}`}>
                      <Text size="xs" ff="monospace">
                        {run.run_id.slice(0, 8)}
                      </Text>
                    </Link>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" ff="monospace">
                      {run.agent_id}
                    </Text>
                  </Table.Td>
                  <Table.Td>{run.agent_version ?? t("common.emptyDash")}</Table.Td>
                  <Table.Td>
                    <Badge size="sm" color={STATUS_COLORS[run.status] ?? "gray"}>
                      {t(`runs.statuses.${run.status}`)}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs">{formatDate(run.created_at)}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs">{formatDate(run.finished_at)}</Text>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Card>
    </Stack>
  );
}
