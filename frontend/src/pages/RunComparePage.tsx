import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { apiFetch } from "../api";
import { PageHeader } from "../components/PageHeader";
import { formatDate } from "../format";
import type {
  Run,
  RunCompareResult,
  RunList,
  RunStatus,
  TrajectoryDigest,
} from "../types";

const STATUS_COLORS: Record<RunStatus, string> = {
  queued: "gray",
  running: "blue",
  waiting_approval: "yellow",
  succeeded: "green",
  failed: "red",
  cancelled: "orange",
};

function renderValue(value: unknown, dash: string): string {
  if (value === null || value === undefined) {
    return dash;
  }
  if (Array.isArray(value)) {
    return value.length === 0 ? dash : value.map((item) => String(item)).join(", ");
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function RunSummary({
  run,
  digest,
  title,
}: {
  run: Run;
  digest: TrajectoryDigest;
  title: string;
}) {
  const { t } = useTranslation();
  return (
    <Card withBorder>
      <Stack gap="xs">
        <Group justify="space-between">
          <Text fw={600}>{title}</Text>
          <Badge size="sm" color={STATUS_COLORS[run.status] ?? "gray"}>
            {t(`runs.statuses.${run.status}`)}
          </Badge>
        </Group>
        <Text size="sm">
          {t("runs.columns.run")}:{" "}
          <Text span ff="monospace">
            {run.run_id.slice(0, 12)}
          </Text>
        </Text>
        <Text size="sm">
          {t("runs.columns.agent")}:{" "}
          <Text span ff="monospace">
            {run.agent_id}
          </Text>{" "}
          · v{run.agent_version ?? t("common.emptyDash")}
        </Text>
        <Text size="sm">
          {t("runDetail.harnessHash")}:{" "}
          <Text span ff="monospace">
            {run.harness_hash?.slice(0, 12) ?? t("common.emptyDash")}
          </Text>
        </Text>
        <Text size="sm">
          {t("runDetail.digestSteps")}: {digest.steps} ·{" "}
          {t("runDetail.digestDuration")}:{" "}
          {digest.duration_ms === null
            ? t("common.emptyDash")
            : `${(digest.duration_ms / 1000).toFixed(1)} s`}
        </Text>
        <Text size="sm">
          {t("runDetail.digestToolCalls")}: {digest.total_tool_calls} ·{" "}
          {t("runDetail.digestErrors")}: {digest.failed_tool_calls}
        </Text>
        <Text size="sm">
          {t("runDetail.digestTokens")}: {digest.total_tokens ?? t("common.emptyDash")}
        </Text>
        <Text size="sm">
          {t("runs.columns.created")}: {formatDate(run.created_at)}
        </Text>
        {digest.error ? (
          <Alert color="red" variant="light">
            {digest.error}
          </Alert>
        ) : null}
        <Button component={Link} to={`/runs/${encodeURIComponent(run.run_id)}`} variant="light" size="xs">
          {t("runCompare.openRun")}
        </Button>
      </Stack>
    </Card>
  );
}

export function RunComparePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const left = searchParams.get("left") ?? "";
  const right = searchParams.get("right") ?? "";
  const [runs, setRuns] = useState<Run[]>([]);
  const [runsLoading, setRunsLoading] = useState(true);
  const [result, setResult] = useState<RunCompareResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<RunList>("/v1/runs?limit=200")
      .then((data) => {
        if (!cancelled) {
          setRuns(data.items ?? []);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRuns([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setRunsLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!left || !right) {
      setResult(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiFetch<RunCompareResult>(
      `/v1/runs/compare?left=${encodeURIComponent(left)}&right=${encodeURIComponent(right)}`,
    )
      .then((value) => {
        if (!cancelled) {
          setResult(value);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setResult(null);
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [left, right]);

  const options = useMemo(
    () =>
      runs.map((run) => ({
        value: run.run_id,
        label: `${run.run_id.slice(0, 8)} · ${run.agent_id} · ${run.status} · ${formatDate(run.created_at)}`,
      })),
    [runs],
  );

  const askAssistant = () => {
    if (!result) {
      return;
    }
    const changed = result.diff
      .filter((item) => item.changed)
      .map(
        (item) =>
          `${item.field}: ${renderValue(item.left, "—")} → ${renderValue(item.right, "—")}`,
      )
      .join("\n");
    const assistMessage = t("runCompare.assistPrompt", {
      agent: result.left.agent_id,
      left: result.left.run_id,
      right: result.right.run_id,
      diff: changed || t("runCompare.noDiff"),
      leftDigest: JSON.stringify(result.left_digest),
      rightDigest: JSON.stringify(result.right_digest),
      differentAgents:
        result.left.agent_id !== result.right.agent_id
          ? t("runCompare.differentAgents")
          : "",
    });
    navigate(`/agents/${encodeURIComponent(result.left.agent_id)}`, {
      state: { assistMessage },
    });
  };

  return (
    <Stack gap="md">
      <PageHeader title={t("runCompare.title")}>
        {result ? (
          <Button variant="default" onClick={() => navigate("/runs")}>
            {t("runCompare.back")}
          </Button>
        ) : null}
      </PageHeader>

      {!left || !right ? (
        <Card withBorder>
          <Stack gap="sm">
            <Text size="sm" c="dimmed">
              {t("runCompare.pickTwo")}
            </Text>
            {runsLoading ? (
              <Loader size="sm" />
            ) : (
              <Group align="flex-end" wrap="wrap">
                <Select
                  label={t("runCompare.left")}
                  data={options}
                  searchable
                  w={360}
                  value={left || null}
                  onChange={(value) => {
                    const next = new URLSearchParams(searchParams);
                    if (value) {
                      next.set("left", value);
                    } else {
                      next.delete("left");
                    }
                    setSearchParams(next);
                  }}
                />
                <Select
                  label={t("runCompare.right")}
                  data={options}
                  searchable
                  w={360}
                  value={right || null}
                  onChange={(value) => {
                    const next = new URLSearchParams(searchParams);
                    if (value) {
                      next.set("right", value);
                    } else {
                      next.delete("right");
                    }
                    setSearchParams(next);
                  }}
                />
                <Button
                  disabled={!left || !right || left === right}
                  onClick={() => setSearchParams({ left, right })}
                >
                  {t("runCompare.submit")}
                </Button>
              </Group>
            )}
          </Stack>
        </Card>
      ) : loading ? (
        <Group justify="center" p="xl">
          <Loader size="sm" />
        </Group>
      ) : error ? (
        <Alert color="red" title={t("common.loadError")}>
          {error}
        </Alert>
      ) : result ? (
        <>
          <SimpleGrid cols={{ base: 1, lg: 2 }}>
            <RunSummary run={result.left} digest={result.left_digest} title={t("runCompare.left")} />
            <RunSummary
              run={result.right}
              digest={result.right_digest}
              title={t("runCompare.right")}
            />
          </SimpleGrid>

          <Card withBorder>
            <Stack gap="sm">
              <Group justify="space-between" wrap="wrap">
                <Text fw={600}>{t("runCompare.diffTitle")}</Text>
                <Group gap="xs">
                  <Button variant="default" onClick={() => navigate("/runs")}>
                    {t("runCompare.back")}
                  </Button>
                  <Button
                    variant="light"
                    onClick={() =>
                      navigate(`/agents/${encodeURIComponent(result.left.agent_id)}`)
                    }
                  >
                    {t("runCompare.openAgent")}
                  </Button>
                  <Button onClick={askAssistant}>{t("runCompare.askAssistant")}</Button>
                </Group>
              </Group>
              <Table.ScrollContainer minWidth={760}>
                <Table withTableBorder withColumnBorders>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>{t("runCompare.field")}</Table.Th>
                      <Table.Th>{t("runCompare.leftColumn")}</Table.Th>
                      <Table.Th>{t("runCompare.rightColumn")}</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {result.diff.map((item) => (
                      <Table.Tr
                        key={item.field}
                        style={
                          item.changed
                            ? { background: "var(--mantine-color-yellow-light)" }
                            : undefined
                        }
                      >
                        <Table.Td>
                          <Text size="sm" ff="monospace">
                            {item.field}
                          </Text>
                        </Table.Td>
                        <Table.Td>{renderValue(item.left, t("common.emptyDash"))}</Table.Td>
                        <Table.Td>{renderValue(item.right, t("common.emptyDash"))}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </Stack>
          </Card>
        </>
      ) : null}
    </Stack>
  );
}
