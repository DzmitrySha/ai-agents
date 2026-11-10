import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Code,
  Drawer,
  Group,
  Loader,
  Modal,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
  Title,
  Tabs,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { apiFetch, asItems, errorMessage, jsonBody } from "../api";
import { roleOf, useSession } from "../components/AppLayout";
import { FIELD_ORDER, NO_AUTOFILL } from "../formAttrs";
import { useAssistForm } from "../assist";
import {
  IconAction,
  PageHeader,
  PageSearch,
  readViewMode,
  saveViewMode,
  ViewToggle,
  type ViewMode,
} from "../components/PageHeader";
import { PlusIcon } from "../components/icons";
import { formatDate } from "../format";
import type {
  Skill,
  SkillDetail,
  SkillFile,
  SkillList,
  SkillLocalFileEntry,
  SkillLocalImportResult,
  SkillSuggestion,
} from "../types";
import { useBaselineDirty, useUnsavedGuard } from "../unsavedChanges";

const EMPTY_SKILL_DRAFT = { name: "", slug: "", description: "", content: "" };
const SKILLS_SH_URL = "https://skills.sh/";

/** Навыки: свой SKILL.md, импорт с skills.sh / с компьютера, просмотр, удаление. */
export function SkillsPage() {
  const { t } = useTranslation();
  const me = useSession();
  const canWrite = roleOf(me) !== "user";
  const [skills, setSkills] = useState<Skill[]>([]);
  const [view, setView] = useState<ViewMode>(() => readViewMode("skills"));
  const [importOpen, setImportOpen] = useState(false);
  const [mode, setMode] = useState<string | null>("manual");
  const [draft, setDraft] = useState(EMPTY_SKILL_DRAFT);
  const [editing, setEditing] = useState<{ slug: string; source: string } | null>(null);
  const [assistPrompt, setAssistPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [savingSkill, setSavingSkill] = useState(false);
  const [skillFormError, setSkillFormError] = useState<string | null>(null);
  const [assistHints, setAssistHints] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [importUrl, setImportUrl] = useState("");
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [localImporting, setLocalImporting] = useState(false);
  const [localImportError, setLocalImportError] = useState<string | null>(null);
  const [localPending, setLocalPending] = useState<SkillLocalFileEntry[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const [filter, setFilter] = useState("");

  const skillModalDraft = { draft, assistPrompt, importUrl };
  const { dirty: skillDirty, captureBaseline: captureSkill } = useBaselineDirty(
    skillModalDraft,
    importOpen && canWrite,
  );

  useAssistForm(
    "skill",
    importOpen
      ? {
          page_search: filter,
          name: draft.name,
          slug: draft.slug,
          description: draft.description,
          content: draft.content,
          taken_slugs: skills.map((skill) => skill.slug),
        }
      : { page_search: filter, taken_slugs: skills.map((skill) => skill.slug) },
    (fields) => {
      const { page_search: _ps, ...rest } = fields;
      const next = { ...draft };
      let touched = false;
      for (const key of ["name", "slug", "description", "content"] as const) {
        const value = rest[key];
        if (typeof value === "string" && (value.trim() || key === "description" || key === "content")) {
          if (key === "slug" && editing) {
            continue;
          }
          next[key] = value;
          touched = true;
        }
      }
      if (!touched) {
        return Object.keys(rest).length === 0 ? null : t("skills.noFieldsFromModel");
      }
      if (!importOpen) {
        captureSkill({
          draft: EMPTY_SKILL_DRAFT,
          assistPrompt: "",
          importUrl: "",
        });
      }
      setDraft(next);
      setMode("manual");
      setImportOpen(true);
      return null;
    },
    (query) => {
      setFilter(query);
      return null;
    },
  );

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<Skill | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSkills(asItems(await apiFetch<SkillList>("/v1/skills")));
    } catch (err) {
      setError(errorMessage(err));
      setSkills([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const importSkill = async (url: string) => {
    const value = url.trim();
    if (!value) {
      setImportError(t("skills.importUrlRequired"));
      return;
    }
    setImporting(true);
    setImportError(null);
    try {
      const imported = await apiFetch<SkillDetail>("/v1/skills/import", {
        method: "POST",
        body: jsonBody({ url: value }),
      });
      setNotice(t("skills.imported", { name: imported.name }));
      setImportUrl("");
      await load();
    } catch (err) {
      setImportError(errorMessage(err));
    } finally {
      setImporting(false);
    }
  };

  const applyLocalImportResult = async (result: SkillLocalImportResult) => {
    const names = result.items.map((item) => item.name).join(", ");
    const parts = [
      result.created ? t("skills.importStatsCreated", { count: result.created }) : null,
      result.updated ? t("skills.importStatsUpdated", { count: result.updated }) : null,
      result.skipped.length
        ? t("skills.importStatsSkipped", { count: result.skipped.length })
        : null,
    ].filter(Boolean);
    const partsJoined = parts.join(", ");
    setNotice(
      result.items.length === 1
        ? t("skills.importSingle", { name: result.items[0].name, parts: partsJoined })
        : t("skills.importMulti", { parts: partsJoined, names }),
    );
    setLocalPending([]);
    setLocalImportError(null);
    await load();
  };

  const clearFileInputs = () => {
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    if (folderInputRef.current) {
      folderInputRef.current.value = "";
    }
  };

  const clearLocalPending = () => {
    setLocalPending([]);
    setLocalImportError(null);
    clearFileInputs();
  };

  const pickBrowserFiles = async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) {
      return;
    }
    const entries: SkillLocalFileEntry[] = [];
    for (const file of Array.from(fileList)) {
      const relative =
        (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
      if (!/\.(md|txt|json|ya?ml|toml)$/i.test(relative)) {
        continue;
      }
      entries.push({ path: relative.replace(/\\/g, "/"), content: await file.text() });
    }
    clearFileInputs();
    if (entries.length === 0) {
      setLocalPending([]);
      setLocalImportError(t("skills.noSkillMd"));
      return;
    }
    setLocalImportError(null);
    setLocalPending(entries);
  };

  const confirmLocalImport = async () => {
    if (localPending.length === 0) {
      setLocalImportError(t("skills.pickFirst"));
      return;
    }
    setLocalImporting(true);
    setLocalImportError(null);
    try {
      const result = await apiFetch<SkillLocalImportResult>("/v1/skills/import-local", {
        method: "POST",
        body: jsonBody({ entries: localPending }),
      });
      await applyLocalImportResult(result);
    } catch (err) {
      setLocalImportError(errorMessage(err));
    } finally {
      setLocalImporting(false);
    }
  };

  const changeView = (value: ViewMode) => {
    setView(value);
    saveViewMode("skills", value);
  };

  const closeSkillModal = () => {
    clearLocalPending();
    setImportOpen(false);
  };

  const openCreate = () => {
    setEditing(null);
    const next = {
      draft: EMPTY_SKILL_DRAFT,
      assistPrompt: "",
      importUrl: "",
    };
    setDraft(next.draft);
    setAssistPrompt(next.assistPrompt);
    setImportUrl(next.importUrl);
    setAssistHints([]);
    setSkillFormError(null);
    clearLocalPending();
    setMode("manual");
    captureSkill(next);
    setImportOpen(true);
  };

  const openEditSkill = async (skill: Skill) => {
    setEditing({ slug: skill.slug, source: skill.source });
    const placeholder = {
      draft: { name: skill.name, slug: skill.slug, description: skill.description, content: "" },
      assistPrompt: "",
      importUrl: "",
    };
    setDraft(placeholder.draft);
    setAssistPrompt("");
    setImportUrl("");
    setAssistHints([]);
    setSkillFormError(null);
    setMode("manual");
    captureSkill(placeholder);
    setImportOpen(true);
    try {
      const detail = await apiFetch<SkillDetail>(`/v1/skills/${encodeURIComponent(skill.slug)}`);
      const loaded = {
        draft: {
          name: detail.name,
          slug: detail.slug,
          description: detail.description,
          content: detail.content,
        },
        assistPrompt: "",
        importUrl: "",
      };
      setDraft(loaded.draft);
      captureSkill(loaded);
    } catch (err) {
      setSkillFormError(errorMessage(err));
    }
  };

  const generateSkill = async () => {
    const description = assistPrompt.trim();
    if (description.length < 3) {
      setSkillFormError(t("skills.describeRequired"));
      return;
    }
    setGenerating(true);
    setSkillFormError(null);
    setAssistHints([]);
    try {
      const result = await apiFetch<SkillSuggestion>("/v1/assist/skill", {
        method: "POST",
        body: jsonBody({ description }),
      });
      setDraft({
        name: result.name,
        slug: editing?.slug ?? result.slug,
        description: result.description,
        content: result.content,
      });
      setAssistHints([...(result.notes ? [result.notes] : []), ...result.warnings]);
    } catch (err) {
      setSkillFormError(errorMessage(err));
    } finally {
      setGenerating(false);
    }
  };

  const persistManualSkill = async () => {
    if (!draft.name.trim()) {
      throw new Error(t("skills.nameRequired"));
    }
    if (!draft.content.trim()) {
      throw new Error(t("skills.contentRequired"));
    }
    if (editing) {
      await apiFetch<SkillDetail>(`/v1/skills/${encodeURIComponent(editing.slug)}`, {
        method: "PATCH",
        body: jsonBody({ description: draft.description, content: draft.content }),
      });
      setNotice(t("skills.saved", { name: draft.name }));
    } else {
      const created = await apiFetch<SkillDetail>("/v1/skills", {
        method: "POST",
        body: jsonBody({
          name: draft.name.trim(),
          slug: draft.slug.trim() || null,
          description: draft.description,
          content: draft.content,
        }),
      });
      setNotice(t("skills.created", { name: created.name }));
    }
    captureSkill({ draft, assistPrompt, importUrl });
    closeSkillModal();
    await load();
  };

  const saveManualSkill = async () => {
    setSavingSkill(true);
    setSkillFormError(null);
    try {
      await persistManualSkill();
    } catch (err) {
      setSkillFormError(errorMessage(err));
    } finally {
      setSavingSkill(false);
    }
  };

  const { requestLeave: requestSkillLeave } = useUnsavedGuard(
    "skill-modal",
    importOpen && canWrite && skillDirty,
    mode === "manual"
      ? async () => {
          setSkillFormError(null);
          try {
            await persistManualSkill();
          } catch (err) {
            setSkillFormError(errorMessage(err));
            throw err;
          }
        }
      : undefined,
  );

  const openSkill = async (skill: Skill) => {
    setDrawerOpen(true);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      setDetail(await apiFetch<SkillDetail>(`/v1/skills/${encodeURIComponent(skill.slug)}`));
    } catch (err) {
      setDetailError(errorMessage(err));
    } finally {
      setDetailLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) {
      return;
    }
    setDeleting(true);
    setDeleteError(null);
    try {
      await apiFetch<void>(`/v1/skills/${encodeURIComponent(deleteTarget.slug)}`, {
        method: "DELETE",
      });
      setNotice(t("skills.deleted", { name: deleteTarget.name }));
      setDeleteTarget(null);
      await load();
    } catch (err) {
      setDeleteError(errorMessage(err));
    } finally {
      setDeleting(false);
    }
  };

  const needle = filter.trim().toLowerCase();
  const visible = needle
    ? skills.filter((skill) =>
        [skill.name, skill.slug, skill.description]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(needle)),
      )
    : skills;

  if (importOpen) {
    return (
      <Stack gap="md">
        <Group justify="space-between" align="center">
          <Title order={2}>
            {editing ? t("skills.editTitle", { name: draft.name }) : t("skills.addTitle")}
          </Title>
          <Button variant="default" onClick={() => requestSkillLeave(closeSkillModal)}>
            {t("common.backToList")}
          </Button>
        </Group>

        <Tabs value={mode} onChange={setMode}>
          <Tabs.List>
            <Tabs.Tab value="manual">{t("skills.tabs.manual")}</Tabs.Tab>
            <Tabs.Tab value="import" disabled={Boolean(editing)}>
              {t("skills.tabs.import")}
            </Tabs.Tab>
            <Tabs.Tab value="local" disabled={Boolean(editing)}>
              {t("skills.tabs.local")}
            </Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="manual" pt="md">
            <Stack gap="sm">
              {skillFormError ? (
                <Alert color="red" title={t("common.saveFailed")}>
                  {skillFormError}
                </Alert>
              ) : null}

              <Card withBorder bg="var(--mantine-color-default-hover)">
                <Stack gap="xs">
                  <Text fw={600}>{t("skills.aiTitle")}</Text>
                  <Text size="xs" c="dimmed">
                    {t("skills.aiHint")}
                  </Text>
                  <Textarea
                    {...NO_AUTOFILL}
                    placeholder={t("skills.aiPlaceholder")}
                    value={assistPrompt}
                    onChange={(event) => setAssistPrompt(event.currentTarget.value)}
                    minRows={2}
                    autosize
                  />
                  <Group>
                    <Button
                      variant="light"
                      onClick={() => void generateSkill()}
                      loading={generating}
                    >
                      {t("common.generate")}
                    </Button>
                  </Group>
                  {assistHints.map((hint) => (
                    <Text key={hint} size="xs" c="orange">
                      {hint}
                    </Text>
                  ))}
                </Stack>
              </Card>

              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <TextInput
                  {...NO_AUTOFILL}
                  inputWrapperOrder={[...FIELD_ORDER]}
                  label={t("common.name")}
                  value={draft.name}
                  onChange={(event) => {
                    const value = event.currentTarget.value;
                    setDraft((prev) => ({ ...prev, name: value }));
                  }}
                  required
                />
                <TextInput
                  {...NO_AUTOFILL}
                  inputWrapperOrder={[...FIELD_ORDER]}
                  label={t("common.slug")}
                  description={t("skills.slugHint")}
                  value={draft.slug}
                  readOnly={Boolean(editing)}
                  onChange={(event) => {
                    const value = event.currentTarget.value;
                    setDraft((prev) => ({ ...prev, slug: value }));
                  }}
                />
              </SimpleGrid>
              <TextInput
                {...NO_AUTOFILL}
                label={t("common.description")}
                value={draft.description}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  setDraft((prev) => ({ ...prev, description: value }));
                }}
              />

              <Textarea
                {...NO_AUTOFILL}
                label={t("skills.contentLabel")}
                description={t("skills.contentHint")}
                value={draft.content}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  setDraft((prev) => ({ ...prev, content: value }));
                }}
                minRows={14}
                autosize
                ff="monospace"
              />
              <Group>
                <Button onClick={() => void saveManualSkill()} loading={savingSkill}>
                  {editing ? t("common.save") : t("common.create")}
                </Button>
                <Button variant="default" onClick={() => requestSkillLeave(closeSkillModal)}>
                  {t("common.cancel")}
                </Button>
              </Group>
            </Stack>
          </Tabs.Panel>

          <Tabs.Panel value="import" pt="md">
            <Card withBorder>
              <Stack gap="sm">
                <Text fw={600}>{t("skills.importUrlTitle")}</Text>
                <Text size="sm" c="dimmed">
                  {t("skills.importUrlHint")}{" "}
                  <Anchor href={SKILLS_SH_URL} target="_blank" rel="noreferrer">
                    skills.sh
                  </Anchor>
                </Text>
                <Group align="flex-end" wrap="nowrap">
                  <TextInput
                    {...NO_AUTOFILL}
                    style={{ flex: 1 }}
                    label={t("skills.importUrlLabel")}
                    placeholder="https://skills.sh/owner/repo/skill"
                    value={importUrl}
                    onChange={(event) => setImportUrl(event.currentTarget.value)}
                  />
                  <Button onClick={() => void importSkill(importUrl)} loading={importing}>
                    {t("skills.importButton")}
                  </Button>
                </Group>
                {importError ? (
                  <Alert color="red" title={t("skills.importFailed")}>
                    {importError}
                  </Alert>
                ) : null}
              </Stack>
            </Card>
          </Tabs.Panel>

          <Tabs.Panel value="local" pt="md">
            <Card withBorder>
              <Stack gap="sm">
                <Text fw={600}>{t("skills.localTitle")}</Text>
                <Text size="sm" c="dimmed">
                  {t("skills.localHint")}
                </Text>
                <Group gap="sm">
                  <Button
                    variant="light"
                    disabled={localImporting}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    {t("skills.pickFile")}
                  </Button>
                  <Button
                    variant="light"
                    disabled={localImporting}
                    onClick={() => folderInputRef.current?.click()}
                  >
                    {t("skills.pickFolder")}
                  </Button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".md,text/markdown,text/plain"
                    multiple
                    hidden
                    onChange={(event) => void pickBrowserFiles(event.currentTarget.files)}
                  />
                  <input
                    ref={(node) => {
                      folderInputRef.current = node;
                      if (node) {
                        node.setAttribute("webkitdirectory", "");
                        node.setAttribute("directory", "");
                      }
                    }}
                    type="file"
                    hidden
                    multiple
                    onChange={(event) => void pickBrowserFiles(event.currentTarget.files)}
                  />
                </Group>
                {localPending.length > 0 ? (
                  <Alert color="blue" title={t("skills.readyToImport")}>
                    <Stack gap="xs">
                      <Text size="sm">
                        {t("skills.selectedFiles", { count: localPending.length })}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {localPending.length <= 10
                          ? localPending.map((entry) => entry.path).join(", ")
                          : `${localPending
                              .slice(0, 8)
                              .map((entry) => entry.path)
                              .join(", ")}… (+${localPending.length - 8})`}
                      </Text>
                      <Group gap="sm">
                        <Button onClick={() => void confirmLocalImport()} loading={localImporting}>
                          {t("skills.importButton")}
                        </Button>
                        <Button
                          variant="default"
                          disabled={localImporting}
                          onClick={clearLocalPending}
                        >
                          {t("common.reset")}
                        </Button>
                      </Group>
                    </Stack>
                  </Alert>
                ) : null}
                {localImportError ? (
                  <Alert color="red" title={t("skills.importFailed")}>
                    {localImportError}
                  </Alert>
                ) : null}
              </Stack>
            </Card>
          </Tabs.Panel>

        </Tabs>
      </Stack>
    );
  }

  return (
    <Stack gap="md">
      <PageHeader title={t("skills.title")} count={skills.length}>
        <PageSearch value={filter} onChange={setFilter} />
        <ViewToggle value={view} onChange={changeView} />
        <IconAction
          kind="refresh"
          label={t("common.refresh")}
          onClick={() => void load()}
          loading={loading}
        />
        {canWrite ? (
          <Button onClick={openCreate} leftSection={<PlusIcon />}>
            {t("skills.add")}
          </Button>
        ) : null}
      </PageHeader>

      <Text size="sm" c="dimmed">
        {t("skills.intro")}
      </Text>

      {error ? (
        <Alert color="red" title={t("common.loadError")}>
          {error}
        </Alert>
      ) : null}
      {notice ? (
        <Alert color="green" withCloseButton onClose={() => setNotice(null)}>
          {notice}
        </Alert>
      ) : null}

      <Group gap="sm">
        <Text fw={600}>{t("skills.installed")}</Text>
        <Badge variant="light">{skills.length}</Badge>
      </Group>

      {loading ? (
        <Group justify="center" p="xl">
          <Loader size="sm" />
        </Group>
      ) : visible.length === 0 ? (
        <Text size="sm" c="dimmed">
          {skills.length === 0 ? t("skills.empty") : t("skills.emptyFilter")}
        </Text>
      ) : view === "table" ? (
        <Card withBorder padding={0}>
          <Table.ScrollContainer minWidth={760}>
          <Table striped highlightOnHover withTableBorder verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("common.name")}</Table.Th>
                <Table.Th>{t("common.slug")}</Table.Th>
                <Table.Th>{t("skills.source")}</Table.Th>
                <Table.Th>{t("common.updated")}</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {visible.map((skill) => (
                <Table.Tr key={skill.id ?? skill.slug}>
                  <Table.Td>
                    <Text size="sm">{skill.name}</Text>
                    <Text size="xs" c="dimmed">
                      {skill.description}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Code>{skill.slug}</Code>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" c="dimmed">
                      {skill.source}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs">{formatDate(skill.updated_at)}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={6} justify="flex-end" wrap="nowrap">
                      {canWrite && skill.source === "manual" ? (
                        <IconAction
                          kind="edit"
                          label={t("common.edit")}
                          onClick={() => void openEditSkill(skill)}
                        />
                      ) : null}
                      <IconAction
                        kind="open"
                        label={t("common.open")}
                        onClick={() => void openSkill(skill)}
                      />
                      <IconAction
                        kind="delete"
                        label={t("common.delete")}
                        onClick={() => {
                          setDeleteError(null);
                          setDeleteTarget(skill);
                        }}
                      />
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          </Table.ScrollContainer>
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }} spacing="md">
          {visible.map((skill) => (
            <Card key={skill.id ?? skill.slug} withBorder>
              <Stack gap="xs" h="100%">
                <Group justify="space-between" align="flex-start" wrap="nowrap" gap="xs">
                  <Text size="sm" fw={600} lineClamp={2}>
                    {skill.name}
                  </Text>
                  <Badge size="xs" variant="light" color={skill.source === "skills.sh" ? "blue" : "gray"}>
                    {skill.source}
                  </Badge>
                </Group>
                <Code style={{ fontSize: 11 }}>{skill.slug}</Code>
                {skill.description ? (
                  <Text size="xs" c="dimmed" lineClamp={3}>
                    {skill.description}
                  </Text>
                ) : null}
                <Group justify="space-between" mt="auto" align="center">
                  <Text size="xs" c="dimmed">
                    {formatDate(skill.updated_at)}
                  </Text>
                  <Group gap={6} wrap="nowrap">
                    {canWrite && skill.source === "manual" ? (
                      <IconAction
                        kind="edit"
                        label={t("common.edit")}
                        onClick={() => void openEditSkill(skill)}
                      />
                    ) : null}
                    <IconAction
                      kind="open"
                      label={t("common.open")}
                      onClick={() => void openSkill(skill)}
                    />
                    <IconAction
                      kind="delete"
                      label={t("common.delete")}
                      onClick={() => {
                        setDeleteError(null);
                        setDeleteTarget(skill);
                      }}
                    />
                  </Group>
                </Group>
              </Stack>
            </Card>
          ))}
        </SimpleGrid>
      )}

      <Modal
        opened={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        title={t("skills.deleteTitle")}
        size="sm"
      >
        <Stack gap="sm">
          <Text size="sm">
            {deleteTarget ? t("skills.deleteBody", { name: deleteTarget.name }) : ""}
          </Text>
          {deleteError ? (
            <Alert color="red" title={t("common.deleteFailed")}>
              {deleteError}
            </Alert>
          ) : null}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setDeleteTarget(null)}>
              {t("common.cancel")}
            </Button>
            <Button color="red" onClick={() => void handleDelete()} loading={deleting}>
              {t("common.delete")}
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Drawer
        opened={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        position="right"
        size="xl"
        title={detail?.name ?? t("skills.detailTitle")}
      >
        <Stack gap="sm">
          {detailLoading ? (
            <Group justify="center" p="xl">
              <Loader size="sm" />
            </Group>
          ) : null}
          {detailError ? (
            <Alert color="red" title={t("common.loadError")}>
              {detailError}
            </Alert>
          ) : null}
          {detail ? (
            <Stack gap="sm">
              <Group gap="xs">
                <Badge variant="light">{detail.source}</Badge>
                {detail.source_id ? (
                  <Text size="xs" c="dimmed" ff="monospace">
                    {detail.source_id}
                  </Text>
                ) : null}
              </Group>
              {detail.description ? (
                <Text size="sm" c="dimmed">
                  {detail.description}
                </Text>
              ) : null}
              {detail.source_url ? (
                <Anchor href={detail.source_url} target="_blank" rel="noreferrer" size="sm">
                  {detail.source_url}
                </Anchor>
              ) : null}
              <Text fw={600}>{t("skills.content")}</Text>
              <Code block style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>
                {detail.content || t("common.emptyParen")}
              </Code>
              <Text fw={600}>{t("skills.filesCount", { count: detail.files?.length ?? 0 })}</Text>
              {(detail.files ?? []).length === 0 ? (
                <Text size="sm" c="dimmed">
                  {t("skills.noExtraFiles")}
                </Text>
              ) : (
                <Stack gap="sm">
                  {(detail.files ?? []).map((file) => {
                    const body =
                      file.contents ||
                      (file as SkillFile & { content?: string }).content ||
                      t("common.emptyParen");
                    return (
                      <Stack key={file.path} gap={4}>
                        <Text size="xs" fw={600} ff="monospace">
                          {file.path}
                        </Text>
                        <Code block style={{ whiteSpace: "pre-wrap", fontSize: 11 }}>
                          {body}
                        </Code>
                      </Stack>
                    );
                  })}
                </Stack>
              )}
            </Stack>
          ) : null}
        </Stack>
      </Drawer>
    </Stack>
  );
}
