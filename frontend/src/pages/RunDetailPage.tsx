import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Anchor,
  Badge,
  Breadcrumbs,
  Button,
  Card,
  Code,
  Grid,
  Group,
  Loader,
  Modal,
  ScrollArea,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { ApiError, apiFetch, jsonBody } from "../api";
import { useAssistForm } from "../assist";
import { NO_AUTOFILL } from "../formAttrs";
import { formatDate, formatValue } from "../format";
import { matchesPageSearch } from "../pageSearch";
import { Markdown } from "../components/Markdown";
import { formatStreamEvent, streamedText, useRunStream } from "../useRunStream";
import {
  isTerminalRun,
  type Run,
  type RunApproval,
  type RunHarness,
  type RunList,
  type RunStatus,
  type TrajectoryDigest,
} from "../types";

const STATUS_COLORS: Record<RunStatus, string> = {
  queued: "gray",
  running: "blue",
  waiting_approval: "yellow",
  succeeded: "green",
  failed: "red",
  cancelled: "orange",
};

export function RunDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [run, setRun] = useState<Run | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [repeating, setRepeating] = useState(false);
  const [harness, setHarness] = useState<RunHarness | null>(null);
  const [harnessOpen, setHarnessOpen] = useState(false);
  const [harnessFailed, setHarnessFailed] = useState(false);
  const [digest, setDigest] = useState<TrajectoryDigest | null>(null);
  const [digestFailed, setDigestFailed] = useState(false);
  const [transcriptError, setTranscriptError] = useState<string | null>(null);
  const [approvals, setApprovals] = useState<RunApproval[]>([]);
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const [deciding, setDeciding] = useState<string | null>(null);
  const [children, setChildren] = useState<Run[]>([]);
  const [pageSearch, setPageSearch] = useState("");

  const runId = id ?? null;
  const { events, finished } = useRunStream(runId);

  const visibleEvents = useMemo(() => {
    if (!pageSearch.trim()) {
      return events;
    }
    return events.filter((ev) => matchesPageSearch(pageSearch, [ev.event, ev.raw]));
  }, [events, pageSearch]);

  useAssistForm(
    "general",
    {
      page_search: pageSearch,
      run_id: run?.run_id ?? runId,
      agent_id: run?.agent_id,
      status: run?.status,
      events_tail: events.slice(-30).map((ev) => ({ event: ev.event, sample: ev.raw.slice(0, 240) })),
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
    if (!runId) {
      return;
    }
    try {
      const value = await apiFetch<Run>(`/v1/runs/${encodeURIComponent(runId)}`);
      setRun(value);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (finished) {
      void load();
    }
  }, [finished, load]);

  useEffect(() => {
    const hash = run?.harness_hash;
    if (!runId || !hash) {
      setHarness(null);
      setHarnessFailed(false);
      return;
    }
    let cancelled = false;
    setHarnessFailed(false);
    apiFetch<RunHarness>(`/v1/runs/${encodeURIComponent(runId)}/harness`)
      .then((value) => {
        if (!cancelled) {
          setHarness(value);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setHarness(null);
          setHarnessFailed(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [runId, run?.harness_hash]);

  useEffect(() => {
    if (!runId) {
      setDigest(null);
      setDigestFailed(false);
      return;
    }
    let cancelled = false;
    setDigestFailed(false);
    apiFetch<TrajectoryDigest>(`/v1/runs/${encodeURIComponent(runId)}/digest`)
      .then((value) => {
        if (!cancelled) {
          setDigest(value);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setDigest(null);
          setDigestFailed(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [runId, run?.status]);

  useEffect(() => {
    if (!runId) {
      setApprovals([]);
      return;
    }
    let cancelled = false;
    apiFetch<RunApproval[]>(`/v1/runs/${encodeURIComponent(runId)}/approvals`)
      .then((value) => {
        if (!cancelled) {
          setApprovals(value);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setApprovals([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [runId, run?.status]);

  const handleApproval = async (approvalId: string, decision: "approve" | "reject") => {
    if (!runId) {
      return;
    }
    setDeciding(approvalId);
    setApprovalError(null);
    try {
      await apiFetch<RunApproval>(
        `/v1/runs/${encodeURIComponent(runId)}/approvals/${encodeURIComponent(approvalId)}`,
        { method: "POST", body: jsonBody({ decision }) },
      );
      await load();
    } catch (err) {
      setApprovalError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeciding(null);
    }
  };

  useEffect(() => {
    if (!runId) {
      setChildren([]);
      return;
    }
    let cancelled = false;
    apiFetch<RunList>(
      `/v1/runs?parent_run_id=${encodeURIComponent(runId)}&limit=100`,
    )
      .then((value) => {
        if (!cancelled) {
          setChildren(value.items ?? []);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setChildren([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [runId, run?.status]);

  const pendingApproval = approvals.find((item) => item.status === "pending");

  const handleCancel = async () => {
    if (!runId) {
      return;
    }
    setCancelling(true);
    setError(null);
    try {
      await apiFetch<unknown>(`/v1/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCancelling(false);
    }
  };

  const handleTranscript = async () => {
    if (!runId) {
      return;
    }
    setTranscriptError(null);
    try {
      const data = await apiFetch<unknown>(
        `/v1/runs/${encodeURIComponent(runId)}/transcript`,
      );
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `run-${runId}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      if (err instanceof ApiError && err.status === 410) {
        setTranscriptError(t("runDetail.transcriptArchived"));
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    }
  };

  const handleRepeat = async () => {
    if (!run) {
      return;
    }
    setRepeating(true);
    setError(null);
    try {
      const created = await apiFetch<{ run_id: string }>("/v1/runs", {
        method: "POST",
        body: jsonBody({ agent_id: run.agent_id, input: run.input }),
      });
      navigate(`/runs/${encodeURIComponent(created.run_id)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRepeating(false);
    }
  };

  if (loading) {
    return (
      <Group justify="center" p="xl">
        <Loader size="sm" />
      </Group>
    );
  }

  if (!run) {
    return (
      <Stack>
        <Alert color="red" title={t("runDetail.notFound")}>
          {error ?? t("runDetail.noData")}
        </Alert>
        <Button variant="default" onClick={() => navigate("/runs")}>
          {t("runDetail.backToList")}
        </Button>
      </Stack>
    );
  }

  const terminal = isTerminalRun(run.status);
  const liveText = streamedText(events);

  return (
    <Stack gap="md">
      <Breadcrumbs separator="→" fz="sm">
        <Anchor component={Link} to="/runs" c="dimmed">
          {t("runDetail.breadcrumb")}
        </Anchor>
        <Text c="dimmed" ff="monospace">
          {run.run_id.slice(0, 8)}
        </Text>
      </Breadcrumbs>
      <Group justify="space-between">
        <Group gap="sm">
          <Title order={2}>{t("runDetail.title")}</Title>
          <Text ff="monospace" size="sm" c="dimmed">
            {run.run_id}
          </Text>
          <Badge color={STATUS_COLORS[run.status] ?? "gray"}>
            {t(`runs.statuses.${run.status}`)}
          </Badge>
          {run.failure_kind ? (
            <Badge color="red" variant="light">
              {run.failure_kind}
            </Badge>
          ) : null}
        </Group>
        <Group gap="sm">
          <Button variant="default" onClick={() => navigate("/runs")}>
            {t("runDetail.backShort")}
          </Button>
          <Button
            variant="light"
            onClick={() => void handleRepeat()}
            loading={repeating}
            disabled={!run.agent_id}
            title={t("runDetail.repeatTitle")}
          >
            {t("runDetail.repeat")}
          </Button>
          <Button
            variant="default"
            onClick={() => void handleTranscript()}
            disabled={!runId}
            title={t("runDetail.downloadTranscript")}
          >
            {t("runDetail.downloadTranscript")}
          </Button>
          <Button
            color="red"
            variant="light"
            onClick={() => void handleCancel()}
            loading={cancelling}
            disabled={terminal}
          >
            {t("runDetail.cancel")}
          </Button>
        </Group>
      </Group>

      {error ? (
        <Alert color="red" title={t("common.error")}>
          {error}
        </Alert>
      ) : null}
      {transcriptError ? (
        <Alert color="yellow" variant="light">
          {transcriptError}
        </Alert>
      ) : null}
      {pendingApproval ? (
        <Alert color="yellow" title={t("runDetail.approvalRequired")}>
          <Stack gap="xs">
            <Text size="sm">
              {t("runDetail.approvalTool")}:{" "}
              <Text span ff="monospace">
                {pendingApproval.tool}
              </Text>
            </Text>
            <Code block style={{ whiteSpace: "pre-wrap" }}>
              {formatValue(pendingApproval.input)}
            </Code>
            {approvalError ? (
              <Text size="sm" c="red">
                {t("runDetail.approvalError")}: {approvalError}
              </Text>
            ) : null}
            <Group gap="xs">
              <Button
                color="green"
                size="xs"
                loading={deciding === pendingApproval.id}
                onClick={() => void handleApproval(pendingApproval.id, "approve")}
              >
                {t("runDetail.approve")}
              </Button>
              <Button
                color="red"
                variant="light"
                size="xs"
                loading={deciding === pendingApproval.id}
                onClick={() => void handleApproval(pendingApproval.id, "reject")}
              >
                {t("runDetail.reject")}
              </Button>
            </Group>
          </Stack>
        </Alert>
      ) : null}

      <Grid>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Card withBorder>
            <Stack gap="xs">
              <Text fw={600}>{t("runDetail.params")}</Text>
              <Text size="sm">
                {t("runDetail.agent")}{" "}
                <Text span ff="monospace">
                  {run.agent_id}
                </Text>
              </Text>
              <Text size="sm">
                {t("runDetail.version")} {run.agent_version ?? t("common.emptyDash")}
              </Text>
              <Text size="sm">
                {t("runDetail.attempts")} {run.attempts ?? t("common.emptyDash")}
              </Text>
              {run.parent_run_id ? (
                <Text size="sm">
                  {t("runDetail.parent")}{" "}
                  <Anchor component={Link} to={`/runs/${encodeURIComponent(run.parent_run_id)}`} ff="monospace">
                    {run.parent_run_id.slice(0, 8)}
                  </Anchor>
                  {" · "}
                  {t("runDetail.depth")} {run.depth}
                </Text>
              ) : null}
              <Text size="sm">
                {t("runDetail.created")} {formatDate(run.created_at)}
              </Text>
              <Text size="sm">
                {t("runDetail.started")} {formatDate(run.started_at)}
              </Text>
              <Text size="sm">
                {t("runDetail.finished")} {formatDate(run.finished_at)}
              </Text>
            </Stack>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Card withBorder>
            <Stack gap="xs">
              <Text fw={600}>{t("runDetail.input")}</Text>
              <Code block style={{ whiteSpace: "pre-wrap" }}>
                {formatValue(run.input)}
              </Code>
              {run.metadata ? (
                <>
                  <Text fw={600}>{t("runDetail.metadata")}</Text>
                  <Code block style={{ whiteSpace: "pre-wrap" }}>
                    {formatValue(run.metadata)}
                  </Code>
                </>
              ) : null}
            </Stack>
          </Card>
        </Grid.Col>
      </Grid>

      <Card withBorder>
        <Stack gap="xs">
          <Group justify="space-between" align="center">
            <Text fw={600}>{t("runDetail.harness")}</Text>
            {run.harness_hash ? (
              <Button
                size="compact-xs"
                variant="light"
                disabled={!harness?.snapshot}
                onClick={() => setHarnessOpen(true)}
              >
                {t("runDetail.showHarness")}
              </Button>
            ) : null}
          </Group>
          {!run.harness_hash ? (
            <Text size="sm" c="dimmed">
              {t("runDetail.harnessUnavailable")}
            </Text>
          ) : harnessFailed ? (
            <Text size="sm" c="dimmed">
              {t("runDetail.harnessUnavailable")}
            </Text>
          ) : !harness?.snapshot ? (
            <Group gap="xs">
              <Loader size="xs" />
              <Text size="sm" c="dimmed">
                {t("common.loading")}
              </Text>
            </Group>
          ) : (
            <Stack gap={4}>
              <Text size="xs" c="dimmed" ff="monospace">
                {t("runDetail.harnessHash")}: {harness.harness_hash?.slice(0, 12)}
              </Text>
              <Text size="sm">
                {t("runDetail.harnessModel")}:{" "}
                <Text span ff="monospace">
                  {harness.snapshot.llm.model ?? t("common.emptyDash")}
                </Text>
              </Text>
              <Text size="sm">
                {t("runDetail.harnessLimits")}: max_steps={harness.snapshot.limits.max_steps},{" "}
                timeout={harness.snapshot.limits.timeout_seconds}s
                {harness.snapshot.limits.max_tokens
                  ? `, max_tokens=${harness.snapshot.limits.max_tokens}`
                  : ""}
                {harness.snapshot.limits.max_attempts
                  ? `, max_attempts=${harness.snapshot.limits.max_attempts}`
                  : ""}
                {harness.snapshot.retry?.fallback_model
                  ? `, fallback=${harness.snapshot.retry.fallback_model}`
                  : ""}
                {harness.snapshot.context
                  ? `, context=${harness.snapshot.context.max_tokens} tokens, skills=${harness.snapshot.context.skills_mode}`
                  : ""}
              </Text>
              <Text size="sm">
                {t("runDetail.harnessTools")}: {harness.snapshot.tools.length} ·{" "}
                {t("runDetail.harnessSkills")}: {harness.snapshot.skills.length} ·{" "}
                {t("runDetail.harnessMcp")}: {harness.snapshot.mcp.length} ·{" "}
                {t("agentEditor.subAgents")}: {harness.snapshot.sub_agents?.length ?? 0}
              </Text>
            </Stack>
          )}
        </Stack>
      </Card>

      <Card withBorder>
        <Stack gap="sm">
          <Text fw={600}>{t("runDetail.digest")}</Text>
          {digestFailed ? (
            <Text size="sm" c="dimmed">
              {t("runDetail.digestUnavailable")}
            </Text>
          ) : !digest ? (
            <Group gap="xs">
              <Loader size="xs" />
              <Text size="sm" c="dimmed">
                {t("common.loading")}
              </Text>
            </Group>
          ) : (
            <>
              <Group gap="lg" wrap="wrap">
                <Text size="sm">
                  {t("runDetail.digestSteps")}: {digest.steps}
                </Text>
                <Text size="sm">
                  {t("runDetail.digestDuration")}:{" "}
                  {digest.duration_ms === null
                    ? t("common.emptyDash")
                    : `${(digest.duration_ms / 1000).toFixed(1)} s`}
                </Text>
                <Text size="sm">
                  {t("runDetail.digestEvents")}: {digest.events_total}
                </Text>
                <Text size="sm">
                  {t("runDetail.digestOutputChars")}: {digest.output_chars}
                </Text>
                <Text size="sm">
                  {t("runDetail.digestTokens")}:{" "}
                  {digest.prompt_tokens ?? t("common.emptyDash")} /{" "}
                  {digest.completion_tokens ?? t("common.emptyDash")} /{" "}
                  {digest.total_tokens ?? t("common.emptyDash")}
                </Text>
                <Text size="sm">
                  {t("runDetail.attempts")}: {digest.attempts ?? t("common.emptyDash")}
                  {digest.failure_kind
                    ? ` · ${t("runDetail.failureKind")}: ${digest.failure_kind}`
                    : ""}
                </Text>
              </Group>
              {digest.tool_calls.length === 0 ? (
                <Text size="sm" c="dimmed">
                  {t("runDetail.digestNoTools")}
                </Text>
              ) : (
                <Table withTableBorder withColumnBorders>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>{t("runDetail.digestTool")}</Table.Th>
                      <Table.Th>{t("runDetail.digestCalls")}</Table.Th>
                      <Table.Th>{t("runDetail.digestErrors")}</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {digest.tool_calls.map((call) => (
                      <Table.Tr key={call.tool}>
                        <Table.Td>
                          <Text size="sm" ff="monospace">
                            {call.tool}
                          </Text>
                        </Table.Td>
                        <Table.Td>{call.calls}</Table.Td>
                        <Table.Td>
                          <Text
                            size="sm"
                            c={call.errors > 0 ? "red" : undefined}
                            fw={call.errors > 0 ? 600 : undefined}
                          >
                            {call.errors}
                          </Text>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
              {digest.unfinished_tool_calls > 0 ? (
                <Text size="sm" c="orange">
                  {t("runDetail.digestUnfinished", {
                    count: digest.unfinished_tool_calls,
                  })}
                </Text>
              ) : null}
              {digest.error ? (
                <Alert color="red" variant="light">
                  {digest.error}
                </Alert>
              ) : null}
            </>
          )}
        </Stack>
      </Card>

      <Card withBorder>
        <Stack gap="sm">
          <Text fw={600}>{t("runDetail.children")}</Text>
          {children.length === 0 ? (
            <Text size="sm" c="dimmed">
              {t("runDetail.noChildren")}
            </Text>
          ) : (
            <Table withTableBorder withColumnBorders>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("runs.columns.run")}</Table.Th>
                  <Table.Th>{t("runs.columns.agent")}</Table.Th>
                  <Table.Th>{t("runs.columns.status")}</Table.Th>
                  <Table.Th>{t("runDetail.depth")}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {children.map((child) => (
                  <Table.Tr key={child.run_id}>
                    <Table.Td>
                      <Anchor component={Link} to={`/runs/${encodeURIComponent(child.run_id)}`} ff="monospace">
                        {child.run_id.slice(0, 8)}
                      </Anchor>
                    </Table.Td>
                    <Table.Td>{child.agent_id}</Table.Td>
                    <Table.Td>
                      <Badge color={STATUS_COLORS[child.status] ?? "gray"}>
                        {t(`runs.statuses.${child.status}`)}
                      </Badge>
                    </Table.Td>
                    <Table.Td>{child.depth}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Stack>
      </Card>

      <Card withBorder>
        <Stack gap="sm">
          <Text fw={600}>{t("runDetail.result")}</Text>
          {run.error ? (
            <Alert color="red" variant="light">
              {run.error}
            </Alert>
          ) : null}
          {liveText ? <Markdown>{liveText}</Markdown> : null}
          {run.output !== null && run.output !== undefined ? (
            <Markdown>{formatValue(run.output)}</Markdown>
          ) : terminal && !run.error ? (
            <Text size="sm" c="dimmed">
              {t("runDetail.emptyOutput")}
            </Text>
          ) : null}
        </Stack>
      </Card>

      <Card withBorder>
        <Stack gap="sm">
          <Group justify="space-between" align="flex-end" wrap="wrap">
            <Text fw={600}>{t("runDetail.events")}</Text>
            <Group gap="sm" align="flex-end">
              <TextInput
                {...NO_AUTOFILL}
                aria-label={t("common.search")}
                placeholder={t("common.pageSearchPlaceholder")}
                value={pageSearch}
                onChange={(event) => setPageSearch(event.currentTarget.value)}
                w={260}
              />
              <Text size="xs" c="dimmed">
                {t("runDetail.eventsReceived", { count: events.length })}
              </Text>
            </Group>
          </Group>
          <ScrollArea h={320} type="auto">
            {events.length === 0 ? (
              <Text size="sm" c="dimmed">
                {t("runDetail.eventsEmpty")}
              </Text>
            ) : visibleEvents.length === 0 ? (
              <Text size="sm" c="dimmed">
                {t("common.emptyPageFilter")}
              </Text>
            ) : (
              <Code block style={{ whiteSpace: "pre-wrap", fontSize: 11 }}>
                {visibleEvents.map(formatStreamEvent).join("\n")}
              </Code>
            )}
          </ScrollArea>
        </Stack>
      </Card>

      <Modal
        opened={harnessOpen}
        onClose={() => setHarnessOpen(false)}
        title={t("runDetail.harnessTitle")}
        size="lg"
      >
        <Stack gap="sm">
          {harness?.snapshot ? (
            <ScrollArea h={520} type="auto">
              <Code block style={{ whiteSpace: "pre-wrap", fontSize: 11 }}>
                {JSON.stringify(harness.snapshot, null, 2)}
              </Code>
            </ScrollArea>
          ) : null}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setHarnessOpen(false)}>
              {t("runDetail.close")}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
