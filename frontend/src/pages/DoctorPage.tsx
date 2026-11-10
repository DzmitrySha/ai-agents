import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Code,
  Group,
  Loader,
  Modal,
  Stack,
  Table,
  Text,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { apiFetch } from "../api";
import { PageHeader } from "../components/PageHeader";
import { formatDate } from "../format";
import type { DoctorCheck, DoctorResult } from "../types";

const STATUS_COLORS: Record<DoctorCheck["status"], string> = {
  ok: "green",
  warn: "yellow",
  error: "red",
  skip: "gray",
};

function detailValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "—";
  }
  if (Array.isArray(value)) {
    return value.length ? value.map((item) => String(item)).join(", ") : "—";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  if (typeof value === "boolean") {
    return value ? "yes" : "no";
  }
  return String(value);
}

function detailBadges(
  check: DoctorCheck,
  labels: Record<string, string>,
): { key: string; label: string; value: string }[] {
  return Object.entries(check.details)
    .filter(([, value]) => {
      if (value === null || value === undefined) {
        return false;
      }
      if (Array.isArray(value)) {
        return value.length > 0;
      }
      if (typeof value === "object") {
        return Object.keys(value as Record<string, unknown>).length > 0;
      }
      return true;
    })
    .map(([key, value]) => ({
      key,
      label: labels[key] ?? key,
      value: detailValue(value),
    }));
}

function DetailBadges({
  check,
  labels,
}: {
  check: DoctorCheck;
  labels: Record<string, string>;
}) {
  const badges = detailBadges(check, labels);
  if (badges.length === 0) {
    return (
      <Text size="xs" c="dimmed">
        —
      </Text>
    );
  }
  return (
    <Group gap={6}>
      {badges.map((badge) => (
        <Badge key={badge.key} size="md" variant="light" color="gray" tt="none">
          {badge.label}: {badge.value}
        </Badge>
      ))}
    </Group>
  );
}

export function DoctorPage() {
  const { t } = useTranslation();
  const [data, setData] = useState<DoctorResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detailsCheck, setDetailsCheck] = useState<DoctorCheck | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await apiFetch<DoctorResult>("/v1/doctor"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const labels = t("doctor.fields", { returnObjects: true }) as Record<string, string>;

  return (
    <Stack gap="md">
      <PageHeader title={t("doctor.title")}>
        <Button variant="default" onClick={() => void load()} loading={loading}>
          {t("doctor.refresh")}
        </Button>
      </PageHeader>

      {error ? (
        <Alert color="red" title={t("common.error")}>
          {error}
        </Alert>
      ) : null}

      {loading && !data ? (
        <Loader />
      ) : data ? (
        <>
          <Group gap="sm">
            <Badge color={data.ok ? "green" : "red"} size="lg">
              {data.ok ? t("doctor.ok") : t("doctor.failed")}
            </Badge>
            <Text size="sm" c="dimmed">
              {formatDate(data.generated_at)}
            </Text>
          </Group>
          <Card withBorder>
            <Table.ScrollContainer minWidth={760}>
              <Table striped highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t("doctor.check")}</Table.Th>
                    <Table.Th>{t("doctor.status")}</Table.Th>
                    <Table.Th>{t("doctor.message")}</Table.Th>
                    <Table.Th>{t("doctor.details")}</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {data.checks.map((check) => (
                    <Table.Tr key={check.id}>
                      <Table.Td>
                        <Text size="md" ff="monospace">
                          {check.id}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Badge color={STATUS_COLORS[check.status]} size="md">
                          {t(`doctor.statuses.${check.status}`)}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Text size="md">{check.message}</Text>
                        <Text size="sm" c="dimmed">
                          {check.duration_ms} ms
                        </Text>
                      </Table.Td>
                      <Table.Td
                        onClick={() =>
                          Object.keys(check.details).length
                            ? setDetailsCheck(check)
                            : undefined
                        }
                        style={{
                          cursor: Object.keys(check.details).length
                            ? "pointer"
                            : undefined,
                        }}
                      >
                        <DetailBadges check={check} labels={labels} />
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Card>
          <Modal
            opened={detailsCheck !== null}
            onClose={() => setDetailsCheck(null)}
            title={
              detailsCheck
                ? `${detailsCheck.id} — ${t("doctor.jsonTitle")}`
                : t("doctor.jsonTitle")
            }
            size="lg"
          >
            <Code block style={{ whiteSpace: "pre-wrap", maxHeight: 420, overflow: "auto" }}>
              {detailsCheck ? JSON.stringify(detailsCheck.details, null, 2) : ""}
            </Code>
          </Modal>
        </>
      ) : null}
    </Stack>
  );
}
