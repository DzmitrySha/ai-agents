import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Code,
  Collapse,
  Group,
  Loader,
  Modal,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Text,
  Textarea,
  TextInput,
  Title,
  UnstyledButton,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { apiFetch, asItems, errorMessage, jsonBody } from "../api";
import {
  IconAction,
  PageHeader,
  readViewMode,
  saveViewMode,
  ViewToggle,
  type ViewMode,
} from "../components/PageHeader";
import { PlusIcon } from "../components/icons";
import { FIELD_ORDER, NO_AUTOFILL } from "../formAttrs";
import { useAssistForm } from "../assist";
import { notifySuccess } from "../notify";
import type {
  Tool,
  ToolDeleteResult,
  ToolList,
  ToolMethod,
  ToolParamType,
  ToolPatch,
  ToolSpec,
  ToolSuggestion,
  ToolTestResult,
  ToolUpsert,
  ToolUsage,
} from "../types";
import {
  CONTENT_TYPES,
  EMPTY_TOOL_FORM,
  METHOD_OPTIONS,
  PARAM_TYPE_OPTIONS,
  formFromTool,
  paramsCount,
  parseEnumText,
  parseKeyValueLines,
  type ParamDraft,
  type ToolFormState,
} from "./tools/toolFormUtils";
import { useBaselineDirty, useUnsavedGuard } from "../unsavedChanges";
import { matchesPageSearch } from "../pageSearch";

type CustomToolCardProps = {
  tool: Tool;
  onEdit: (tool: Tool) => void;
  onTest: (tool: Tool) => void;
  onDelete: (tool: Tool) => void;
};

/** Компактная плашка: URL спрятан в Collapse, без горизонтального скролла. */
function CustomToolCard({ tool, onEdit, onTest, onDelete }: CustomToolCardProps) {
  const { t } = useTranslation();
  const [detailsOpen, setDetailsOpen] = useState(false);

  return (
    <Card withBorder style={{ overflow: "hidden", minWidth: 0 }}>
      <Stack gap="xs">
        <Group justify="space-between" gap="xs" wrap="nowrap">
          <Text fw={600} lineClamp={1} style={{ minWidth: 0 }} title={tool.name}>
            {tool.name}
          </Text>
          <Badge variant="light" color={tool.enabled ? "green" : "gray"} style={{ flexShrink: 0 }}>
            {tool.enabled ? t("tools.on") : t("tools.off")}
          </Badge>
        </Group>
        <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
          <Badge variant="outline" style={{ flexShrink: 0 }}>
            {tool.method}
          </Badge>
          <Text size="xs" c="dimmed" ff="monospace" truncate title={tool.slug}>
            {tool.slug}
          </Text>
        </Group>
        {tool.description ? (
          <Text size="sm" c="dimmed" lineClamp={2}>
            {tool.description}
          </Text>
        ) : null}
        <UnstyledButton
          onClick={() => setDetailsOpen((open) => !open)}
          aria-expanded={detailsOpen}
        >
          <Text size="xs" c="blue.5">
            {detailsOpen ? t("tools.hideDetails") : t("tools.showDetails")}
          </Text>
        </UnstyledButton>
        <Collapse expanded={detailsOpen}>
          <Code
            block
            title={tool.url}
            style={{
              fontSize: 11,
              whiteSpace: "pre-wrap",
              overflowWrap: "anywhere",
              wordBreak: "break-word",
              maxWidth: "100%",
            }}
          >
            {tool.url}
          </Code>
        </Collapse>
        <Group gap={6}>
          <IconAction kind="edit" label={t("common.edit")} onClick={() => onEdit(tool)} />
          <IconAction kind="test" label={t("common.test")} onClick={() => onTest(tool)} />
          <IconAction kind="delete" label={t("common.delete")} onClick={() => onDelete(tool)} />
        </Group>
      </Stack>
    </Card>
  );
}

/** Инструменты: встроенные и свои HTTP-инструменты (без кода). */
export function ToolsPage() {
  const { t } = useTranslation();
  const [view, setView] = useState<ViewMode>(() => readViewMode("tools"));

  const [builtinTools, setBuiltinTools] = useState<ToolSpec[]>([]);
  const [customTools, setCustomTools] = useState<Tool[]>([]);
  const [pageSearch, setPageSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [schemaTool, setSchemaTool] = useState<ToolSpec | null>(null);

  // Конструктор инструмента
  const [builderOpen, setBuilderOpen] = useState(false);
  const [editingTool, setEditingTool] = useState<Tool | null>(null);
  const [form, setForm] = useState<ToolFormState>(EMPTY_TOOL_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [assistText, setAssistText] = useState("");
  const [assistBusy, setAssistBusy] = useState(false);
  const [assistHints, setAssistHints] = useState<string[]>([]);
  const builderDraft = useMemo(
    () => ({ form, assistText }),
    [form, assistText],
  );
  const { dirty: builderDirty, captureBaseline: captureBuilder } = useBaselineDirty(
    builderDraft,
    builderOpen,
  );

  const openBuilder = useCallback(() => {
    setBuilderOpen(true);
  }, []);

  const filteredCustomTools = useMemo(
    () =>
      customTools.filter((tool) =>
        matchesPageSearch(pageSearch, [
          tool.name,
          tool.slug,
          tool.description,
          tool.method,
          tool.url,
        ]),
      ),
    [customTools, pageSearch],
  );

  const filteredBuiltinTools = useMemo(
    () =>
      builtinTools.filter((tool) =>
        matchesPageSearch(pageSearch, [tool.name, tool.description, tool.source]),
      ),
    [builtinTools, pageSearch],
  );

  useAssistForm(
    "tool",
    builderOpen
      ? {
          page_search: pageSearch,
          slug: form.slug,
          name: form.name,
          description: form.description,
          method: form.method,
          url: form.url,
          headers: form.headers,
          query: form.query,
          body_template: form.body_template,
          content_type: form.content_type,
          timeout_seconds: form.timeout_seconds,
          parameters: form.parameters,
        }
      : { page_search: pageSearch },
    (fields) => {
      const next: Partial<ToolFormState> = {};
      const stringKeys: (keyof ToolFormState)[] = [
        "slug",
        "name",
        "description",
        "url",
        "body_template",
        "content_type",
      ];
      for (const key of stringKeys) {
        const value = fields[key as string];
        if (typeof value === "string" && value.trim()) {
          (next[key] as unknown) = value;
        }
      }
      if (
        typeof fields.method === "string" &&
        ["GET", "POST", "PUT", "PATCH", "DELETE"].includes(fields.method)
      ) {
        next.method = fields.method as ToolMethod;
      }
      const mapToLines = (value: unknown): string | null => {
        if (!value || typeof value !== "object" || Array.isArray(value)) {
          return null;
        }
        return Object.entries(value as Record<string, unknown>)
          .map(([key, item]) => `${key}: ${String(item)}`)
          .join("\n");
      };
      const headers = mapToLines(fields.headers);
      if (headers !== null) {
        next.headers = headers;
      }
      const query = mapToLines(fields.query);
      if (query !== null) {
        next.query = query;
      }
      const timeout = Number(fields.timeout_seconds);
      if (Number.isFinite(timeout) && timeout >= 1) {
        next.timeout_seconds = Math.min(60, Math.round(timeout));
      }
      if (Array.isArray(fields.parameters)) {
        const drafts: ParamDraft[] = [];
        for (const item of fields.parameters) {
          if (!item || typeof item !== "object") {
            continue;
          }
          const param = item as Record<string, unknown>;
          const name = String(param.name ?? "").trim();
          if (!/^[a-zA-Z_][a-zA-Z0-9_]{0,40}$/.test(name)) {
            continue;
          }
          const type = ["string", "number", "integer", "boolean"].includes(String(param.type))
            ? (param.type as ToolParamType)
            : "string";
          drafts.push({
            name,
            type,
            description: String(param.description ?? ""),
            required: param.required !== false,
            enum: Array.isArray(param.enum) ? param.enum.map(String).join(", ") : "",
          });
        }
        if (drafts.length) {
          next.parameters = drafts;
        }
      }
      if (Object.keys(next).length === 0) {
        return t("tools.noFieldsFromModel");
      }
      if (!builderOpen) {
        captureBuilder({
          form: editingTool ? formFromTool(editingTool) : EMPTY_TOOL_FORM,
          assistText: "",
        });
      }
      setForm((prev) => ({ ...prev, ...next }));
      openBuilder();
      return null;
    },
    (query) => {
      setPageSearch(query);
      return null;
    },
  );

  // Проверка инструмента
  const [testingTool, setTestingTool] = useState<Tool | null>(null);
  const [testParams, setTestParams] = useState("{}");
  const [testBusy, setTestBusy] = useState(false);
  const [testError, setTestError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<ToolTestResult | null>(null);

  // Удаление
  const [deleteTarget, setDeleteTarget] = useState<Tool | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteUsage, setDeleteUsage] = useState<ToolUsage | null>(null);

  const loadTools = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [builtinData, customData] = await Promise.all([
        apiFetch<ToolSpec[]>("/v1/tools"),
        apiFetch<ToolList>("/v1/tools/custom?include_disabled=true"),
      ]);
      setBuiltinTools(asItems(builtinData).filter((tool) => tool.source === "builtin"));
      setCustomTools(asItems(customData));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTools();
  }, [loadTools]);

  const changeView = (value: ViewMode) => {
    setView(value);
    saveViewMode("tools", value);
  };

  const setField = <K extends keyof ToolFormState>(key: K, value: ToolFormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const openCreate = () => {
    setEditingTool(null);
    const next = { form: EMPTY_TOOL_FORM, assistText: "" };
    setForm(next.form);
    setAssistText(next.assistText);
    setAssistHints([]);
    setFormError(null);
    captureBuilder(next);
    setBuilderOpen(true);
  };

  const openEdit = (tool: Tool) => {
    setEditingTool(tool);
    const next = { form: formFromTool(tool), assistText: "" };
    setForm(next.form);
    setAssistText(next.assistText);
    setAssistHints([]);
    setFormError(null);
    captureBuilder(next);
    setBuilderOpen(true);
  };

  const closeBuilder = () => {
    setBuilderOpen(false);
    setEditingTool(null);
  };

  const addParam = () => {
    setForm((prev) => ({
      ...prev,
      parameters: [
        ...prev.parameters,
        { name: "", type: "string", description: "", required: true, enum: "" },
      ],
    }));
  };

  const updateParam = <K extends keyof ParamDraft>(index: number, key: K, value: ParamDraft[K]) => {
    setForm((prev) => ({
      ...prev,
      parameters: prev.parameters.map((param, idx) =>
        idx === index ? { ...param, [key]: value } : param,
      ),
    }));
  };

  const removeParam = (index: number) => {
    setForm((prev) => ({
      ...prev,
      parameters: prev.parameters.filter((_param, idx) => idx !== index),
    }));
  };

  const handleAssistTool = async () => {
    const description = assistText.trim();
    if (description.length < 3) {
      setFormError(t("tools.describeRequired"));
      return;
    }
    setAssistBusy(true);
    setFormError(null);
    setAssistHints([]);
    try {
      const result = await apiFetch<ToolSuggestion>("/v1/assist/tool", {
        method: "POST",
        body: jsonBody({ description }),
      });
      setForm((prev) => ({
        ...prev,
        slug: prev.slug || result.slug,
        name: result.name || prev.name,
        description: result.description || prev.description,
        method: result.method,
        url: result.url || prev.url,
        headers: Object.keys(result.headers).length
          ? Object.entries(result.headers)
              .map(([key, value]) => `${key}: ${value}`)
              .join("\n")
          : prev.headers,
        query: Object.keys(result.query).length
          ? Object.entries(result.query)
              .map(([key, value]) => `${key}: ${value}`)
              .join("\n")
          : prev.query,
        body_template: result.body_template ?? prev.body_template,
        content_type: result.content_type || prev.content_type,
        parameters: result.parameters.length
          ? result.parameters.map((param) => ({
              name: param.name,
              type: param.type,
              description: param.description,
              required: param.required,
              enum: (param.enum ?? []).join(", "),
            }))
          : prev.parameters,
      }));
      setAssistHints([...(result.notes ? [result.notes] : []), ...result.warnings]);
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setAssistBusy(false);
    }
  };

  const persistTool = async () => {
    const slug = form.slug.trim();
    const name = form.name.trim();
    const url = form.url.trim();
    if (!name) {
      throw new Error(t("tools.nameRequired"));
    }
    if (!editingTool && !slug) {
      throw new Error(t("tools.slugRequired"));
    }
    if (!url) {
      throw new Error(t("tools.urlRequired"));
    }
    if (form.parameters.some((param) => !param.name.trim())) {
      throw new Error(t("tools.paramNameRequired"));
    }

    const payload: ToolUpsert = {
      slug,
      name,
      description: form.description.trim(),
      method: form.method,
      url,
      headers: parseKeyValueLines(form.headers),
      query: parseKeyValueLines(form.query),
      body_template: form.body_template.trim() ? form.body_template : null,
      content_type: form.content_type.trim() || "application/json",
      parameters: form.parameters.map((param) => ({
        name: param.name.trim(),
        type: param.type,
        description: param.description.trim(),
        required: param.required,
        enum: parseEnumText(param.enum),
      })),
      timeout_seconds: Number(form.timeout_seconds) || 20,
      enabled: form.enabled,
    };

    if (editingTool) {
      const { slug: _slug, headers, ...rest } = payload;
      const patch: ToolPatch = { ...rest };
      // Empty headers textarea = keep existing secrets; non-empty replaces the map.
      if (form.headers.trim()) {
        patch.headers = headers;
      }
      await apiFetch<Tool>(`/v1/tools/${encodeURIComponent(editingTool.slug)}`, {
        method: "PATCH",
        body: jsonBody(patch),
      });
      setNotice(t("tools.saved", { name }));
      notifySuccess(t("tools.saved", { name }));
    } else {
      await apiFetch<Tool>("/v1/tools", { method: "POST", body: jsonBody(payload) });
      setNotice(t("tools.created", { name }));
      notifySuccess(t("tools.created", { name }));
    }
    captureBuilder({ form, assistText });
    closeBuilder();
    await loadTools();
  };

  const handleSaveTool = async () => {
    setSaving(true);
    setFormError(null);
    try {
      await persistTool();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const { requestLeave: requestBuilderLeave } = useUnsavedGuard(
    "tool-builder",
    builderOpen && builderDirty,
    async () => {
      setFormError(null);
      try {
        await persistTool();
      } catch (err) {
        setFormError(errorMessage(err));
        throw err;
      }
    },
  );

  const openTest = (tool: Tool) => {
    setTestingTool(tool);
    setTestParams("{}");
    setTestResult(null);
    setTestError(null);
  };

  const handleTestTool = async () => {
    if (!testingTool) {
      return;
    }
    let parsed: unknown;
    try {
      parsed = testParams.trim() ? JSON.parse(testParams) : {};
    } catch {
      setTestError(t("tools.testInvalidJson"));
      return;
    }
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      setTestError(t("tools.testExpectObject"));
      return;
    }
    setTestBusy(true);
    setTestError(null);
    setTestResult(null);
    try {
      setTestResult(
        await apiFetch<ToolTestResult>(
          `/v1/tools/${encodeURIComponent(testingTool.slug)}/test`,
          { method: "POST", body: jsonBody({ params: parsed }) },
        ),
      );
    } catch (err) {
      setTestError(errorMessage(err));
    } finally {
      setTestBusy(false);
    }
  };

  const askDeleteTool = (tool: Tool) => {
    setDeleteError(null);
    setDeleteUsage(null);
    setDeleteTarget(tool);
    void apiFetch<ToolUsage>(`/v1/tools/${encodeURIComponent(tool.slug)}/usage`)
      .then((usage) => setDeleteUsage(usage))
      .catch(() => setDeleteUsage(null));
  };

  const handleDelete = async () => {
    if (!deleteTarget) {
      return;
    }
    setDeleting(true);
    setDeleteError(null);
    try {
      const result = await apiFetch<ToolDeleteResult>(
        `/v1/tools/${encodeURIComponent(deleteTarget.slug)}`,
        { method: "DELETE" },
      );
      await loadTools();
      setNotice(
        result.detached_agents.length > 0
          ? t("tools.deletedDetached", {
              name: deleteTarget.name,
              agents: result.detached_agents.join(", "),
            })
          : t("tools.deleted", { name: deleteTarget.name }),
      );
      setDeleteTarget(null);
      setDeleteUsage(null);
    } catch (err) {
      setDeleteError(errorMessage(err));
    } finally {
      setDeleting(false);
    }
  };

  const contentTypeOptions = useMemo(
    () => Array.from(new Set([form.content_type, ...CONTENT_TYPES])).filter(Boolean),
    [form.content_type],
  );

  const total = builtinTools.length + customTools.length;
  const visibleListCount = filteredBuiltinTools.length + filteredCustomTools.length;

  if (builderOpen) {
    return (
      <Stack gap="md">
        <Group justify="space-between" align="center">
          <Title order={2}>
            {editingTool
              ? t("tools.editTitle", { name: editingTool.name })
              : t("tools.newTitle")}
          </Title>
          <Button variant="default" onClick={() => requestBuilderLeave(closeBuilder)}>
            {t("common.backToList")}
          </Button>
        </Group>

        <Stack gap="sm">
          {formError ? (
            <Alert color="red" title={t("common.saveFailed")}>
              {formError}
            </Alert>
          ) : null}

          <Card withBorder bg="var(--mantine-color-default-hover)">
            <Stack gap="xs">
              <Text fw={600}>{t("tools.aiTitle")}</Text>
              <Text size="xs" c="dimmed">
                {t("tools.aiHint")}
              </Text>
              <Textarea
                {...NO_AUTOFILL}
                placeholder={t("tools.aiPlaceholder")}
                value={assistText}
                onChange={(event) => setAssistText(event.currentTarget.value)}
                minRows={2}
                autosize
              />
              <Group>
                <Button variant="light" onClick={() => void handleAssistTool()} loading={assistBusy}>
                  {t("tools.fillFields")}
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
              value={form.name}
              onChange={(event) => setField("name", event.currentTarget.value)}
              required
            />
            <TextInput
              {...NO_AUTOFILL}
              inputWrapperOrder={[...FIELD_ORDER]}
              label={t("common.slug")}
              description={
                editingTool ? t("common.slugImmutable") : t("common.slugHint")
              }
              value={form.slug}
              onChange={(event) => setField("slug", event.currentTarget.value)}
              readOnly={Boolean(editingTool)}
              required
            />
          </SimpleGrid>

          <Textarea
            {...NO_AUTOFILL}
            label={t("common.description")}
            value={form.description}
            onChange={(event) => setField("description", event.currentTarget.value)}
            minRows={2}
            autosize
          />

          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <Select
              label={t("tools.method")}
              data={METHOD_OPTIONS}
              value={form.method}
              onChange={(value) => setField("method", (value as ToolMethod | null) ?? "GET")}
              allowDeselect={false}
            />
            <NumberInput
              {...NO_AUTOFILL}
              label="timeout_seconds"
              min={1}
              max={60}
              value={form.timeout_seconds}
              onChange={(value) => setField("timeout_seconds", value)}
            />
          </SimpleGrid>

          <TextInput
            {...NO_AUTOFILL}
            label={t("tools.url")}
            description={t("tools.urlHint")}
            placeholder={t("tools.urlPlaceholder")}
            value={form.url}
            onChange={(event) => setField("url", event.currentTarget.value)}
            required
          />

          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <Textarea
              {...NO_AUTOFILL}
              label={t("tools.headers")}
              description={
                editingTool
                  ? editingTool.header_names.length
                    ? t("tools.headersHintEditSaved", {
                        names: editingTool.header_names.join(", "),
                      })
                    : t("tools.headersHintEditEmpty")
                  : t("tools.headersHintCreate")
              }
              value={form.headers}
              onChange={(event) => setField("headers", event.currentTarget.value)}
              minRows={4}
              autosize
              ff="monospace"
              placeholder={
                editingTool?.header_names.length
                  ? t("tools.headersKeepPlaceholder")
                  : t("tools.authPlaceholder")
              }
            />
            <Textarea
              {...NO_AUTOFILL}
              label={t("tools.query")}
              description={t("tools.queryHint")}
              value={form.query}
              onChange={(event) => setField("query", event.currentTarget.value)}
              minRows={4}
              autosize
              ff="monospace"
            />
          </SimpleGrid>

          <Textarea
            {...NO_AUTOFILL}
            label={t("tools.bodyTemplate")}
            description={t("tools.bodyTemplateHint")}
            value={form.body_template}
            onChange={(event) => setField("body_template", event.currentTarget.value)}
            minRows={4}
            autosize
            ff="monospace"
          />

          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <Select
              label="content_type"
              data={contentTypeOptions}
              value={form.content_type}
              onChange={(value) => setField("content_type", value ?? "application/json")}
              allowDeselect={false}
              searchable
            />
            <Switch
              label={t("tools.enabled")}
              mt="lg"
              checked={form.enabled}
              onChange={(event) => setField("enabled", event.currentTarget.checked)}
            />
          </SimpleGrid>

          <Group justify="space-between" mt="xs">
            <Text fw={600}>{t("tools.parameters")}</Text>
            <Button size="xs" variant="light" onClick={addParam}>
              {t("tools.addParam")}
            </Button>
          </Group>

          {form.parameters.length === 0 ? (
            <Text size="sm" c="dimmed">
              {t("tools.noParams")}
            </Text>
          ) : (
            <Stack gap="sm">
              {form.parameters.map((param, index) => (
                <Card key={index} withBorder padding="sm">
                  <Stack gap="xs">
                    <SimpleGrid cols={{ base: 1, sm: 3 }}>
                      <TextInput
                        {...NO_AUTOFILL}
                        label={t("tools.paramName")}
                        value={param.name}
                        onChange={(event) => updateParam(index, "name", event.currentTarget.value)}
                        ff="monospace"
                      />
                      <Select
                        label={t("tools.paramType")}
                        data={PARAM_TYPE_OPTIONS}
                        value={param.type}
                        onChange={(value) =>
                          updateParam(index, "type", (value as ToolParamType | null) ?? "string")
                        }
                        allowDeselect={false}
                      />
                      <Switch
                        label={t("tools.paramRequired")}
                        mt="lg"
                        checked={param.required}
                        onChange={(event) =>
                          updateParam(index, "required", event.currentTarget.checked)
                        }
                      />
                    </SimpleGrid>
                    <TextInput
                      {...NO_AUTOFILL}
                      label={t("common.description")}
                      value={param.description}
                      onChange={(event) =>
                        updateParam(index, "description", event.currentTarget.value)
                      }
                    />
                    <Group align="flex-end" wrap="nowrap">
                      <TextInput
                        {...NO_AUTOFILL}
                        style={{ flex: 1 }}
                        label="enum"
                        description={t("tools.paramEnumHint")}
                        value={param.enum}
                        onChange={(event) => updateParam(index, "enum", event.currentTarget.value)}
                      />
                      <Button
                        size="xs"
                        variant="light"
                        color="red"
                        onClick={() => removeParam(index)}
                      >
                        {t("common.delete")}
                      </Button>
                    </Group>
                  </Stack>
                </Card>
              ))}
            </Stack>
          )}

          <Group mt="xs">
            <Button onClick={() => void handleSaveTool()} loading={saving}>
              {editingTool ? t("common.save") : t("common.create")}
            </Button>
            <Button variant="default" onClick={() => requestBuilderLeave(closeBuilder)}>
              {t("common.cancel")}
            </Button>
          </Group>
        </Stack>
      </Stack>
    );
  }

  return (
    <Stack gap="md">
      <PageHeader
        title={t("tools.title")}
        count={pageSearch.trim() ? visibleListCount : total}
      >
        <TextInput
          {...NO_AUTOFILL}
          aria-label={t("common.search")}
          placeholder={t("common.pageSearchPlaceholder")}
          value={pageSearch}
          onChange={(event) => setPageSearch(event.currentTarget.value)}
          w={{ base: "100%", sm: 280 }}
          style={{ flex: "1 1 200px", minWidth: 180, maxWidth: 360 }}
        />
        <ViewToggle value={view} onChange={changeView} />
        <IconAction
          kind="refresh"
          label={t("common.refresh")}
          onClick={() => void loadTools()}
          loading={loading}
        />
        <Button onClick={openCreate} leftSection={<PlusIcon />}>
          {t("tools.add")}
        </Button>
      </PageHeader>

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

      {loading ? (
        <Group justify="center" p="xl">
          <Loader size="sm" />
        </Group>
      ) : view === "table" ? (
        total > 0 && pageSearch.trim() && visibleListCount === 0 ? (
          <Text size="sm" c="dimmed">
            {t("tools.emptyFilter")}
          </Text>
        ) : (
        <Card withBorder padding={0}>
          <Table.ScrollContainer minWidth={960}>
            <Table striped highlightOnHover withTableBorder verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th miw={260}>{t("tools.columns.name")}</Table.Th>
                <Table.Th w={120}>{t("tools.columns.source")}</Table.Th>
                <Table.Th miw={280}>{t("tools.columns.methodUrl")}</Table.Th>
                <Table.Th w={100}>{t("tools.columns.parameters")}</Table.Th>
                <Table.Th w={110}>{t("tools.columns.status")}</Table.Th>
                <Table.Th w={230} />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {filteredCustomTools.map((tool) => (
                <Table.Tr key={tool.id ?? tool.slug}>
                  <Table.Td>
                    <Text size="sm">{tool.name}</Text>
                    <Text size="xs" c="dimmed" lineClamp={2}>
                      {tool.description}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" c="blue.4">
                      {t("tools.sourceCustom")}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={6} wrap="nowrap" mb={2}>
                      <Badge size="sm" variant="outline">
                        {tool.method}
                      </Badge>
                      <Code style={{ fontSize: 11 }}>{tool.slug}</Code>
                    </Group>
                    <Text
                      size="xs"
                      c="dimmed"
                      lineClamp={1}
                      title={tool.url}
                      style={{ overflowWrap: "anywhere", wordBreak: "break-word" }}
                    >
                      {tool.url}
                    </Text>
                  </Table.Td>
                  <Table.Td>{tool.parameters?.length ?? 0}</Table.Td>
                  <Table.Td>
                    <Text size="xs" c={tool.enabled ? "green.6" : "dimmed"}>
                      {tool.enabled ? t("tools.enabledLong") : t("tools.disabledLong")}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={6} justify="flex-end" wrap="nowrap">
                      <IconAction
                        kind="edit"
                        label={t("common.edit")}
                        onClick={() => openEdit(tool)}
                      />
                      <IconAction
                        kind="test"
                        label={t("common.test")}
                        onClick={() => openTest(tool)}
                      />
                      <IconAction
                        kind="delete"
                        label={t("common.delete")}
                        onClick={() => askDeleteTool(tool)}
                      />
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
              {filteredBuiltinTools.map((tool) => (
                <Table.Tr key={tool.name}>
                  <Table.Td>
                    <Text size="sm" ff="monospace">
                      {tool.name}
                    </Text>
                    <Text size="xs" c="dimmed" lineClamp={2}>
                      {tool.description}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" c="dimmed">
                      {t("tools.sourceBuiltin")}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" c="dimmed">
                      {t("common.emptyDash")}
                    </Text>
                  </Table.Td>
                  <Table.Td>{paramsCount(tool.parameters)}</Table.Td>
                  <Table.Td>
                    <Text size="xs" c="dimmed">
                      {t("tools.alwaysAvailable")}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={6} justify="flex-end">
                      <IconAction
                        kind="schema"
                        label={t("tools.schemaParams")}
                        onClick={() => setSchemaTool(tool)}
                      />
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>
        )
      ) : (
        <Stack gap="md">
          <Group gap="sm">
            <Text fw={600}>{t("tools.customSection")}</Text>
            <Badge variant="light">
              {pageSearch.trim() ? filteredCustomTools.length : customTools.length}
            </Badge>
          </Group>

          {customTools.length === 0 ? (
            <Text size="sm" c="dimmed">
              {t("tools.customEmpty")}
            </Text>
          ) : filteredCustomTools.length === 0 ? (
            <Text size="sm" c="dimmed">
              {t("tools.emptyFilter")}
            </Text>
          ) : (
            <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }} spacing="md">
              {filteredCustomTools.map((tool) => (
                <CustomToolCard
                  key={tool.id ?? tool.slug}
                  tool={tool}
                  onEdit={openEdit}
                  onTest={openTest}
                  onDelete={askDeleteTool}
                />
              ))}
            </SimpleGrid>
          )}

          <Group gap="sm" mt="xs">
            <Text fw={600}>{t("tools.builtinSection")}</Text>
            <Badge variant="light">
              {pageSearch.trim() ? filteredBuiltinTools.length : builtinTools.length}
            </Badge>
          </Group>

          {builtinTools.length === 0 ? (
            <Text size="sm" c="dimmed">
              {t("tools.builtinEmpty")}
            </Text>
          ) : filteredBuiltinTools.length === 0 ? (
            <Text size="sm" c="dimmed">
              {t("tools.emptyFilter")}
            </Text>
          ) : (
            <SimpleGrid cols={{ base: 1, sm: 2, md: 3, xl: 4 }} spacing="sm">
              {filteredBuiltinTools.map((tool) => (
                <Card key={tool.name} withBorder padding="sm">
                  <Stack gap={6}>
                    <Group justify="space-between" gap="xs" wrap="nowrap">
                      <Text fw={600} ff="monospace" size="sm">
                        {tool.name}
                      </Text>
                      <Badge variant="light" size="xs">
                        {t("tools.paramsShort", { count: paramsCount(tool.parameters) })}
                      </Badge>
                    </Group>
                    <Text size="xs" c="dimmed" lineClamp={2}>
                      {tool.description || t("common.noDescription")}
                    </Text>
                    <Group justify="flex-end">
                      <IconAction
                        kind="schema"
                        label={t("tools.schemaParams")}
                        onClick={() => setSchemaTool(tool)}
                      />
                    </Group>
                  </Stack>
                </Card>
              ))}
            </SimpleGrid>
          )}
        </Stack>
      )}

      <Modal
        opened={schemaTool !== null}
        onClose={() => setSchemaTool(null)}
        title={
          schemaTool
            ? t("tools.schemaTitle", { name: schemaTool.name })
            : t("tools.schemaShort")
        }
        size="lg"
      >
        <Stack gap="sm">
          <Text size="sm" c="dimmed">
            {schemaTool?.description || t("common.noDescription")}
          </Text>
          <Code block style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>
            {JSON.stringify(schemaTool?.parameters ?? {}, null, 2)}
          </Code>
        </Stack>
      </Modal>

      <Modal
        opened={testingTool !== null}
        onClose={() => setTestingTool(null)}
        title={
          testingTool
            ? t("tools.testTitle", { name: testingTool.name })
            : t("tools.testTitleFallback")
        }
        size="lg"
      >
        <Stack gap="sm">
          <Textarea
            {...NO_AUTOFILL}
            label={t("tools.testParams")}
            description={t("tools.testParamsHint")}
            value={testParams}
            onChange={(event) => setTestParams(event.currentTarget.value)}
            autosize
            minRows={6}
            ff="monospace"
          />
          {testError ? (
            <Alert color="red" title={t("common.error")}>
              {testError}
            </Alert>
          ) : null}
          {testResult ? (
            <Stack gap="xs">
              <Group gap="xs">
                <Badge color={testResult.ok ? "green" : "red"} variant="light">
                  {testResult.ok ? "ok" : "fail"}
                </Badge>
                <Text size="xs" c="dimmed">
                  status: {testResult.status ?? t("common.emptyDash")}
                </Text>
              </Group>
              <Code block style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>
                {testResult.output || t("tools.emptyResponse")}
              </Code>
            </Stack>
          ) : null}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setTestingTool(null)}>
              {t("common.close")}
            </Button>
            <Button onClick={() => void handleTestTool()} loading={testBusy}>
              {t("tools.runTest")}
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Modal
        opened={deleteTarget !== null}
        onClose={() => {
          setDeleteTarget(null);
          setDeleteUsage(null);
        }}
        title={t("tools.deleteTitle")}
        size="sm"
      >
        <Stack gap="sm">
          <Text size="sm">
            {deleteTarget ? t("tools.deleteBody", { name: deleteTarget.name }) : ""}
          </Text>
          {deleteUsage === null ? (
            <Text size="sm" c="dimmed">
              {t("tools.deleteChecking")}
            </Text>
          ) : deleteUsage.total > 0 ? (
            <Alert color="orange" title={t("tools.deleteInUse", { total: deleteUsage.total })}>
              <Text size="sm">{t("tools.deleteDetachHint")}</Text>
              <Text size="sm" mt={4}>
                {deleteUsage.agents
                  .map((agent) =>
                    agent.published_version
                      ? t("tools.publishedAgent", {
                          slug: agent.slug,
                          version: agent.published_version,
                        })
                      : t("tools.draftAgent", { slug: agent.slug }),
                  )
                  .join(", ")}
              </Text>
            </Alert>
          ) : (
            <Text size="sm" c="dimmed">
              {t("tools.deleteUnused")}
            </Text>
          )}
          {deleteError ? (
            <Alert color="red" title={t("common.deleteFailed")}>
              {deleteError}
            </Alert>
          ) : null}
          <Group justify="flex-end">
            <Button
              variant="default"
              onClick={() => {
                setDeleteTarget(null);
                setDeleteUsage(null);
              }}
            >
              {t("common.cancel")}
            </Button>
            <Button color="red" onClick={() => void handleDelete()} loading={deleting}>
              {t("common.delete")}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
