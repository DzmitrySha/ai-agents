import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Modal,
  Stack,
  Table,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { apiFetch, jsonBody } from "../api";
import { PageHeader } from "../components/PageHeader";
import type { Pack, PackInstallResult } from "../types";

const ACTION_COLORS: Record<string, string> = {
  create: "green",
  update: "yellow",
  noop: "gray",
};

export function PacksPage() {
  const { t } = useTranslation();
  const [packs, setPacks] = useState<Pack[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<Pack | null>(null);
  const [result, setResult] = useState<PackInstallResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [manifestText, setManifestText] = useState("");
  const [importError, setImportError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPacks((await apiFetch<Pack[]>("/v1/packs")) ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const run = async (pack: Pack, dryRun: boolean) => {
    setBusy(`${pack.name}:${dryRun ? "dry" : "install"}`);
    setError(null);
    try {
      const outcome = await apiFetch<PackInstallResult>(
        `/v1/packs/${encodeURIComponent(pack.name)}/install?dry_run=${dryRun}`,
        { method: "POST" },
      );
      setActive(pack);
      setResult(outcome);
      if (!dryRun) {
        await load();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const createPack = async () => {
    setSaving(true);
    setImportError(null);
    try {
      const parsed = JSON.parse(manifestText);
      await apiFetch<Pack>("/v1/packs", {
        method: "POST",
        body: jsonBody(parsed),
      });
      setImportOpen(false);
      setManifestText("");
      await load();
    } catch (err) {
      setImportError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const removePack = async (pack: Pack) => {
    if (!window.confirm(t("packs.deleteConfirm", { name: pack.name }))) {
      return;
    }
    setError(null);
    try {
      await apiFetch<unknown>(`/v1/packs/${encodeURIComponent(pack.name)}`, {
        method: "DELETE",
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Stack gap="md">
      <PageHeader title={t("packs.title")}>
        <Group gap="sm">
          <Button variant="default" onClick={() => void load()} loading={loading}>
            {t("packs.refresh")}
          </Button>
          <Button
            onClick={() => {
              setManifestText(
                JSON.stringify(
                  {
                    name: "my-pack",
                    version: "1",
                    description: "",
                    tools: [],
                    skills: [],
                    agents: [
                      {
                        slug: "my-agent",
                        name: "My agent",
                        system_prompt: "You are a helpful assistant.",
                        tools: [],
                        skills: [],
                      },
                    ],
                  },
                  null,
                  2,
                ),
              );
              setImportError(null);
              setImportOpen(true);
            }}
          >
            {t("packs.add")}
          </Button>
        </Group>
      </PageHeader>

      {error ? (
        <Alert color="red" title={t("common.error")}>
          {error}
        </Alert>
      ) : null}

      <Card withBorder>
        {loading && packs.length === 0 ? (
          <Loader />
        ) : packs.length === 0 ? (
          <Text size="sm" c="dimmed">
            {t("packs.empty")}
          </Text>
        ) : (
          <Table.ScrollContainer minWidth={860}>
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("packs.columns.name")}</Table.Th>
                  <Table.Th>{t("packs.columns.description")}</Table.Th>
                  <Table.Th>{t("packs.columns.refs")}</Table.Th>
                  <Table.Th>{t("packs.columns.installed")}</Table.Th>
                  <Table.Th>{t("packs.columns.actions")}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {packs.map((pack) => (
                  <Table.Tr key={pack.name}>
                    <Table.Td>
                      <Stack gap={2}>
                        <Text fw={600}>{pack.name}</Text>
                        <Group gap={6}>
                          <Text size="xs" c="dimmed">
                            v{pack.version}
                          </Text>
                          <Badge size="xs" variant="outline" color={pack.source === "custom" ? "blue" : "gray"}>
                            {t(`packs.sources.${pack.source}`)}
                          </Badge>
                        </Group>
                      </Stack>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{pack.description || "—"}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Stack gap={2}>
                        <Text size="xs">
                          {t("packs.agents")}: {pack.agents.join(", ") || "—"}
                        </Text>
                        <Text size="xs">
                          {t("packs.skills")}: {pack.skills.join(", ") || "—"}
                        </Text>
                        <Text size="xs">
                          {t("packs.tools")}: {pack.tools.join(", ") || "—"}
                        </Text>
                      </Stack>
                    </Table.Td>
                    <Table.Td>
                      {pack.installed_versions.length > 0 ? (
                        <Badge color="green" variant="light">
                          {pack.installed_versions.join(", ")}
                        </Badge>
                      ) : (
                        <Badge color="gray" variant="light">
                          {t("packs.notInstalled")}
                        </Badge>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Group gap="xs" wrap="nowrap">
                        <Button
                          size="xs"
                          variant="default"
                          loading={busy === `${pack.name}:dry`}
                          onClick={() => void run(pack, true)}
                        >
                          {t("packs.dryRun")}
                        </Button>
                        <Button
                          size="xs"
                          loading={busy === `${pack.name}:install`}
                          onClick={() => void run(pack, false)}
                        >
                          {t("packs.install")}
                        </Button>
                        {pack.source === "custom" ? (
                          <Button
                            size="xs"
                            variant="subtle"
                            color="red"
                            onClick={() => void removePack(pack)}
                          >
                            {t("common.delete")}
                          </Button>
                        ) : null}
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
        opened={result !== null}
        onClose={() => setResult(null)}
        title={
          <Title order={4}>
            {result?.name} {result ? `v${result.version}` : ""}
          </Title>
        }
        size="lg"
      >
        {result ? (
          <Stack gap="sm">
            {result.already_installed ? (
              <Alert color="blue">{t("packs.alreadyInstalled")}</Alert>
            ) : result.dry_run ? (
              <Alert color="gray">{t("packs.dryRunHint")}</Alert>
            ) : (
              <Alert color="green">{t("packs.installDone")}</Alert>
            )}
            {result.changes.length === 0 ? (
              <Text size="sm" c="dimmed">
                {t("packs.noChanges")}
              </Text>
            ) : (
              <Table withTableBorder>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t("packs.entity")}</Table.Th>
                    <Table.Th>{t("packs.ref")}</Table.Th>
                    <Table.Th>{t("packs.action")}</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {result.changes.map((change) => (
                    <Table.Tr key={`${change.entity}:${change.ref}`}>
                      <Table.Td>{change.entity}</Table.Td>
                      <Table.Td>
                        <Text size="sm" ff="monospace">
                          {change.ref}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Badge
                          color={ACTION_COLORS[change.action] ?? "gray"}
                          variant="light"
                        >
                          {t(`packs.actions.${change.action}`)}
                        </Badge>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Stack>
        ) : null}
      </Modal>

      <Modal
        opened={importOpen}
        onClose={() => setImportOpen(false)}
        title={<Title order={4}>{t("packs.add")}</Title>}
        size="xl"
      >
        <Stack gap="sm">
          <Text size="sm" c="dimmed">
            {t("packs.importHint")}
          </Text>
          {importError ? (
            <Alert color="red" title={t("common.error")}>
              {importError}
            </Alert>
          ) : null}
          <Textarea
            value={manifestText}
            onChange={(event) => setManifestText(event.currentTarget.value)}
            minRows={16}
            autosize
            maxRows={28}
            styles={{ input: { fontFamily: "monospace", fontSize: 12 } }}
            aria-label={t("packs.manifest")}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setImportOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button onClick={() => void createPack()} loading={saving}>
              {t("packs.save")}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
