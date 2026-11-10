import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Modal,
  Select,
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
import { PageHeader } from "../components/PageHeader";
import { formatDate } from "../format";
import type { AgentList, Schedule, ScheduleList } from "../types";

interface FormState {
  name: string;
  agent_slug: string;
  cron: string;
  timezone: string;
  input: string;
  enabled: boolean;
}

const EMPTY: FormState = {
  name: "",
  agent_slug: "",
  cron: "0 9 * * *",
  timezone: "Europe/Minsk",
  input: "",
  enabled: true,
};

export function SchedulesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [items, setItems] = useState<Schedule[]>([]);
  const [agents, setAgents] = useState<{ value: string; label: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Schedule | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [schedules, agentList] = await Promise.all([
        apiFetch<ScheduleList>("/v1/schedules"),
        apiFetch<AgentList>("/v1/agents?limit=200"),
      ]);
      setItems(asItems(schedules));
      setAgents(
        asItems(agentList).map((agent) => ({
          value: agent.slug,
          label: `${agent.name} (${agent.slug})`,
        })),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY);
    setModalOpen(true);
  };

  const openEdit = (schedule: Schedule) => {
    setEditing(schedule);
    setForm({
      name: schedule.name,
      agent_slug: schedule.agent_slug,
      cron: schedule.cron,
      timezone: schedule.timezone,
      input:
        typeof schedule.input === "string"
          ? schedule.input
          : JSON.stringify(schedule.input),
      enabled: schedule.enabled,
    });
    setModalOpen(true);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const body = {
        name: form.name.trim(),
        agent_slug: form.agent_slug,
        cron: form.cron.trim(),
        timezone: form.timezone.trim() || "UTC",
        input: form.input,
        enabled: form.enabled,
      };
      if (editing) {
        await apiFetch<Schedule>(`/v1/schedules/${encodeURIComponent(editing.id)}`, {
          method: "PATCH",
          body: jsonBody(body),
        });
      } else {
        await apiFetch<Schedule>("/v1/schedules", {
          method: "POST",
          body: jsonBody(body),
        });
      }
      setModalOpen(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const toggle = async (schedule: Schedule) => {
    setBusy(schedule.id);
    setError(null);
    try {
      await apiFetch<Schedule>(`/v1/schedules/${encodeURIComponent(schedule.id)}`, {
        method: "PATCH",
        body: jsonBody({ enabled: !schedule.enabled }),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const runNow = async (schedule: Schedule) => {
    setBusy(schedule.id);
    setError(null);
    try {
      const run = await apiFetch<{ run_id: string }>(
        `/v1/schedules/${encodeURIComponent(schedule.id)}/run-now`,
        { method: "POST" },
      );
      navigate(`/runs/${encodeURIComponent(run.run_id)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const remove = async (schedule: Schedule) => {
    if (!window.confirm(t("schedules.deleteConfirm", { name: schedule.name }))) {
      return;
    }
    setBusy(schedule.id);
    setError(null);
    try {
      await apiFetch<unknown>(`/v1/schedules/${encodeURIComponent(schedule.id)}`, {
        method: "DELETE",
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Stack gap="md">
      <PageHeader title={t("schedules.title")}>
        <Button onClick={openCreate}>{t("schedules.add")}</Button>
      </PageHeader>

      {error ? (
        <Alert color="red" title={t("common.error")}>
          {error}
        </Alert>
      ) : null}

      <Card withBorder>
        {loading ? (
          <Group justify="center" p="md">
            <Loader size="sm" />
          </Group>
        ) : items.length === 0 ? (
          <Text size="sm" c="dimmed">
            {t("schedules.empty")}
          </Text>
        ) : (
          <Table.ScrollContainer minWidth={960}>
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("schedules.columns.name")}</Table.Th>
                  <Table.Th>{t("schedules.columns.agent")}</Table.Th>
                  <Table.Th>{t("schedules.columns.cron")}</Table.Th>
                  <Table.Th>{t("schedules.columns.timezone")}</Table.Th>
                  <Table.Th>{t("schedules.columns.next")}</Table.Th>
                  <Table.Th>{t("schedules.columns.last")}</Table.Th>
                  <Table.Th>{t("schedules.columns.actions")}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {items.map((schedule) => (
                  <Table.Tr key={schedule.id}>
                    <Table.Td>
                      <Stack gap={2}>
                        <Text size="sm">{schedule.name}</Text>
                        <Badge
                          size="xs"
                          variant="light"
                          color={schedule.enabled ? "green" : "gray"}
                        >
                          {schedule.enabled
                            ? t("schedules.enabled")
                            : t("schedules.disabled")}
                        </Badge>
                      </Stack>
                    </Table.Td>
                    <Table.Td>
                      <Text size="xs" ff="monospace">
                        {schedule.agent_slug}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="xs" ff="monospace">
                        {schedule.cron}
                      </Text>
                    </Table.Td>
                    <Table.Td>{schedule.timezone}</Table.Td>
                    <Table.Td>{formatDate(schedule.next_run_at)}</Table.Td>
                    <Table.Td>
                      <Stack gap={2}>
                        <Text size="xs">{formatDate(schedule.last_run_at)}</Text>
                        {schedule.last_error ? (
                          <Text size="xs" c="red" lineClamp={2}>
                            {schedule.last_error}
                          </Text>
                        ) : null}
                      </Stack>
                    </Table.Td>
                    <Table.Td>
                      <Group gap="xs" wrap="nowrap">
                        <Button
                          size="compact-xs"
                          variant="light"
                          loading={busy === schedule.id}
                          onClick={() => void runNow(schedule)}
                        >
                          {t("schedules.runNow")}
                        </Button>
                        <Button
                          size="compact-xs"
                          variant="default"
                          onClick={() => void toggle(schedule)}
                          disabled={busy === schedule.id}
                        >
                          {schedule.enabled
                            ? t("schedules.disable")
                            : t("schedules.enable")}
                        </Button>
                        <Button
                          size="compact-xs"
                          variant="subtle"
                          onClick={() => openEdit(schedule)}
                        >
                          {t("common.edit")}
                        </Button>
                        <Button
                          size="compact-xs"
                          variant="subtle"
                          color="red"
                          onClick={() => void remove(schedule)}
                          disabled={busy === schedule.id}
                        >
                          {t("common.delete")}
                        </Button>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Card>

      <Modal
        opened={modalOpen}
        onClose={() => setModalOpen(false)}
        title={
          <Title order={4}>
            {editing ? t("schedules.editTitle") : t("schedules.newTitle")}
          </Title>
        }
        size="lg"
      >
        <Stack gap="sm">
          <TextInput
            label={t("schedules.name")}
            value={form.name}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, name: event.currentTarget.value }))
            }
          />
          <Select
            label={t("schedules.agent")}
            data={agents}
            searchable
            value={form.agent_slug || null}
            onChange={(value) =>
              setForm((prev) => ({ ...prev, agent_slug: value ?? "" }))
            }
          />
          <TextInput
            label={t("schedules.cron")}
            description={t("schedules.cronHint")}
            value={form.cron}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, cron: event.currentTarget.value }))
            }
          />
          <TextInput
            label={t("schedules.timezone")}
            value={form.timezone}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, timezone: event.currentTarget.value }))
            }
          />
          <Textarea
            label={t("schedules.input")}
            minRows={3}
            value={form.input}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, input: event.currentTarget.value }))
            }
          />
          <Switch
            label={t("schedules.enabled")}
            checked={form.enabled}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, enabled: event.currentTarget.checked }))
            }
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setModalOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button onClick={() => void save()} loading={saving}>
              {t("common.save")}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
