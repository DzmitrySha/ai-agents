import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
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
  TextInput,
  Title,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { apiFetch, jsonBody } from "../api";
import { PageHeader } from "../components/PageHeader";
import { formatDate } from "../format";
import type {
  Delivery,
  DeliveryList,
  NotificationChannel,
} from "../types";

interface FormState {
  name: string;
  kind: "webhook" | "telegram";
  url: string;
  chat_id: string;
  secret: string;
  enabled: boolean;
}

const EMPTY: FormState = {
  name: "",
  kind: "webhook",
  url: "",
  chat_id: "",
  secret: "",
  enabled: true,
};

const DELIVERY_COLORS: Record<Delivery["status"], string> = {
  pending: "yellow",
  sent: "green",
  failed: "red",
};

export function NotificationsPage() {
  const { t } = useTranslation();
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<NotificationChannel | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [channelList, deliveryList] = await Promise.all([
        apiFetch<NotificationChannel[]>("/api/admin/notification-channels"),
        apiFetch<DeliveryList>("/api/admin/deliveries?limit=50"),
      ]);
      setChannels(channelList ?? []);
      setDeliveries(deliveryList.items ?? []);
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

  const openEdit = (channel: NotificationChannel) => {
    setEditing(channel);
    setForm({
      name: channel.name,
      kind: channel.kind,
      url: channel.url ?? "",
      chat_id: channel.chat_id ?? "",
      secret: "",
      enabled: channel.enabled,
    });
    setModalOpen(true);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        name: form.name.trim(),
        url: form.url.trim() || null,
        chat_id: form.chat_id.trim() || null,
        enabled: form.enabled,
      };
      if (form.secret.trim()) {
        body.secret = form.secret.trim();
      }
      if (editing) {
        await apiFetch<NotificationChannel>(
          `/api/admin/notification-channels/${encodeURIComponent(editing.id)}`,
          { method: "PATCH", body: jsonBody(body) },
        );
      } else {
        await apiFetch<NotificationChannel>("/api/admin/notification-channels", {
          method: "POST",
          body: jsonBody({ ...body, kind: form.kind }),
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

  const remove = async (channel: NotificationChannel) => {
    if (!window.confirm(t("notifications.deleteConfirm", { name: channel.name }))) {
      return;
    }
    setError(null);
    try {
      await apiFetch<unknown>(
        `/api/admin/notification-channels/${encodeURIComponent(channel.id)}`,
        { method: "DELETE" },
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Stack gap="md">
      <PageHeader title={t("notifications.title")}>
        <Group gap="sm">
          <Button variant="default" onClick={() => void load()} loading={loading}>
            {t("notifications.refresh")}
          </Button>
          <Button onClick={openCreate}>{t("notifications.add")}</Button>
        </Group>
      </PageHeader>

      {error ? (
        <Alert color="red" title={t("common.error")}>
          {error}
        </Alert>
      ) : null}

      <Card withBorder>
        {loading && channels.length === 0 ? (
          <Loader />
        ) : channels.length === 0 ? (
          <Text size="sm" c="dimmed">
            {t("notifications.empty")}
          </Text>
        ) : (
          <Table.ScrollContainer minWidth={760}>
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("notifications.columns.name")}</Table.Th>
                  <Table.Th>{t("notifications.columns.kind")}</Table.Th>
                  <Table.Th>{t("notifications.columns.target")}</Table.Th>
                  <Table.Th>{t("notifications.columns.status")}</Table.Th>
                  <Table.Th>{t("notifications.columns.actions")}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {channels.map((channel) => (
                  <Table.Tr key={channel.id}>
                    <Table.Td>{channel.name}</Table.Td>
                    <Table.Td>
                      <Badge variant="light">{channel.kind}</Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text size="xs" ff="monospace" lineClamp={2}>
                        {channel.kind === "webhook" ? channel.url : channel.chat_id}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Stack gap={2}>
                        <Badge
                          size="sm"
                          variant="light"
                          color={channel.enabled ? "green" : "gray"}
                        >
                          {channel.enabled
                            ? t("notifications.enabled")
                            : t("notifications.disabled")}
                        </Badge>
                        {channel.secret_configured ? (
                          <Badge size="xs" variant="outline">
                            {t("notifications.secretConfigured")}
                          </Badge>
                        ) : null}
                      </Stack>
                    </Table.Td>
                    <Table.Td>
                      <Group gap="xs">
                        <Button
                          size="compact-xs"
                          variant="subtle"
                          onClick={() => openEdit(channel)}
                        >
                          {t("common.edit")}
                        </Button>
                        <Button
                          size="compact-xs"
                          variant="subtle"
                          color="red"
                          onClick={() => void remove(channel)}
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

      <Card withBorder>
        <Stack gap="sm">
          <Text fw={600}>{t("notifications.deliveries")}</Text>
          {deliveries.length === 0 ? (
            <Text size="sm" c="dimmed">
              {t("notifications.noDeliveries")}
            </Text>
          ) : (
            <Table.ScrollContainer minWidth={760}>
              <Table striped highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t("notifications.columns.run")}</Table.Th>
                    <Table.Th>{t("notifications.columns.channel")}</Table.Th>
                    <Table.Th>{t("notifications.columns.status")}</Table.Th>
                    <Table.Th>{t("notifications.columns.attempts")}</Table.Th>
                    <Table.Th>{t("notifications.columns.created")}</Table.Th>
                    <Table.Th>{t("notifications.columns.error")}</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {deliveries.map((delivery) => (
                    <Table.Tr key={delivery.id}>
                      <Table.Td>
                        <Text size="xs" ff="monospace">
                          <Link to={`/runs/${encodeURIComponent(delivery.run_id)}`}>
                            {delivery.run_id.slice(0, 8)}
                          </Link>
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="xs" ff="monospace">
                          {delivery.channel_id.slice(0, 8)}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Badge
                          size="sm"
                          color={DELIVERY_COLORS[delivery.status]}
                        >
                          {t(`notifications.statuses.${delivery.status}`)}
                        </Badge>
                      </Table.Td>
                      <Table.Td>{delivery.attempts}</Table.Td>
                      <Table.Td>{formatDate(delivery.created_at)}</Table.Td>
                      <Table.Td>
                        <Text size="xs" c="red" lineClamp={2}>
                          {delivery.last_error ?? ""}
                        </Text>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
        </Stack>
      </Card>

      <Modal
        opened={modalOpen}
        onClose={() => setModalOpen(false)}
        title={
          <Title order={4}>
            {editing ? t("notifications.editTitle") : t("notifications.newTitle")}
          </Title>
        }
        size="lg"
      >
        <Stack gap="sm">
          <TextInput
            label={t("notifications.name")}
            value={form.name}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, name: event.currentTarget.value }))
            }
          />
          <Select
            label={t("notifications.kind")}
            data={[
              { value: "webhook", label: "webhook" },
              { value: "telegram", label: "telegram" },
            ]}
            value={form.kind}
            disabled={editing !== null}
            onChange={(value) =>
              setForm((prev) => ({
                ...prev,
                kind: (value as "webhook" | "telegram") ?? "webhook",
              }))
            }
          />
          {form.kind === "webhook" ? (
            <>
              <TextInput
                label={t("notifications.url")}
                placeholder="https://example.com/hook"
                value={form.url}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, url: event.currentTarget.value }))
                }
              />
              <TextInput
                label={t("notifications.secret")}
                description={t("notifications.secretHint")}
                value={form.secret}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, secret: event.currentTarget.value }))
                }
              />
            </>
          ) : (
            <TextInput
              label={t("notifications.chatId")}
              value={form.chat_id}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, chat_id: event.currentTarget.value }))
              }
            />
          )}
          <Switch
            label={t("notifications.enabled")}
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
