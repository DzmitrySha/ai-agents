import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Autocomplete,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Modal,
  PasswordInput,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { apiFetch, jsonBody } from "../api";
import { useSession } from "../components/AppLayout";
import { PageHeader, PageSearch } from "../components/PageHeader";
import { FIELD_ORDER, NO_AUTOFILL } from "../formAttrs";
import { useAssistForm } from "../assist";
import { formatDate } from "../format";
import { matchesPageSearch } from "../pageSearch";
import {
  LLM_AUTH_TYPES,
  LLM_PROVIDER_PRESETS,
  type LLMAuthType,
  type LLMModelsResult,
  type LLMProvider,
  type LLMProvidersState,
} from "../types";
import { useBaselineDirty, useUnsavedGuard } from "../unsavedChanges";

const AUTH_I18N_KEY: Record<LLMAuthType, "bearer" | "custom" | "none"> = {
  bearer: "bearer",
  header: "custom",
  none: "none",
};

const PRESET_I18N_KEY: Record<string, "openaiCompat" | "lmStudio" | "ollama" | "anthropicGateway"> = {
  openai: "openaiCompat",
  lmstudio: "lmStudio",
  ollama: "ollama",
  "anthropic-gateway": "anthropicGateway",
};

function providerDraftFrom(
  provider: LLMProvider,
  overrides?: Partial<{
    name: string;
    baseUrl: string;
    model: string;
    apiKey: string;
    authType: LLMAuthType;
    authHeader: string;
    authPrefix: string;
  }>,
) {
  return {
    name: overrides?.name ?? provider.name,
    baseUrl: overrides?.baseUrl ?? provider.base_url,
    model: overrides?.model ?? provider.model,
    apiKey: overrides?.apiKey ?? "",
    authType: overrides?.authType ?? provider.auth_type ?? "bearer",
    authHeader: overrides?.authHeader ?? provider.auth_header ?? "Authorization",
    authPrefix: overrides?.authPrefix ?? provider.auth_prefix ?? "Bearer ",
  };
}

function ProviderCard({
  provider,
  active,
  canEdit,
  onChanged,
  onError,
  onNotice,
}: {
  provider: LLMProvider;
  active: boolean;
  canEdit: boolean;
  onChanged: (state: LLMProvidersState) => void;
  onError: (message: string | null) => void;
  onNotice: (message: string | null) => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState(provider.name);
  const [baseUrl, setBaseUrl] = useState(provider.base_url);
  const [model, setModel] = useState(provider.model);
  const [apiKey, setApiKey] = useState("");
  const [authType, setAuthType] = useState<LLMAuthType>(provider.auth_type ?? "bearer");
  const [authHeader, setAuthHeader] = useState(provider.auth_header ?? "Authorization");
  const [authPrefix, setAuthPrefix] = useState(provider.auth_prefix ?? "Bearer ");
  const [preset, setPreset] = useState<string | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const cardDraft = {
    name,
    baseUrl,
    model,
    apiKey,
    authType,
    authHeader,
    authPrefix,
  };
  const { dirty: cardDirty, captureBaseline: captureCard } = useBaselineDirty(
    cardDraft,
    canEdit,
  );

  const authOptions = useMemo(
    () =>
      LLM_AUTH_TYPES.map((item) => ({
        value: item.value,
        label: t(`llmSettings.authTypes.${AUTH_I18N_KEY[item.value]}.short`),
      })),
    [t],
  );

  const presetOptions = useMemo(
    () =>
      LLM_PROVIDER_PRESETS.map((item) => ({
        value: item.value,
        label: t(`llmSettings.presets.${PRESET_I18N_KEY[item.value]}.label`),
      })),
    [t],
  );

  useEffect(() => {
    const next = providerDraftFrom(provider);
    setName(next.name);
    setBaseUrl(next.baseUrl);
    setModel(next.model);
    setApiKey("");
    setAuthType(next.authType);
    setAuthHeader(next.authHeader);
    setAuthPrefix(next.authPrefix);
    setPreset(
      LLM_PROVIDER_PRESETS.find(
        (item) => item.base_url && item.base_url === next.baseUrl.trim(),
      )?.value ?? null,
    );
    captureCard(next);
    // Только после загрузки/сохранения этой карточки, не при чужом setState.
  }, [provider.id, provider.updated_at, captureCard]);

  const run = async (key: string, action: () => Promise<void>) => {
    setBusy(key);
    onError(null);
    onNotice(null);
    try {
      await action();
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const applyPreset = (value: string | null) => {
    setPreset(value);
    const found = LLM_PROVIDER_PRESETS.find((item) => item.value === value);
    if (!found) {
      return;
    }
    if (found.base_url) {
      setBaseUrl(found.base_url);
    }
    setAuthType(found.auth_type);
    setAuthHeader(found.auth_header);
    setAuthPrefix(found.auth_prefix);
    if (!name.trim()) {
      const label = presetOptions.find((item) => item.value === value)?.label;
      if (label) {
        setName(label);
      }
    }
  };

  const loadModels = () =>
    run("models", async () => {
      const result = await apiFetch<LLMModelsResult>("/v1/settings/llm/models", {
        method: "POST",
        body: jsonBody({
          base_url: baseUrl.trim() || provider.base_url,
          api_key: apiKey.trim() || null,
          auth_type: authType,
          auth_header: authHeader.trim() || "Authorization",
          auth_prefix: authPrefix,
        }),
      });
      setModels(result.models);
      onNotice(t("llmSettings.modelsFetched", { name: provider.name, count: result.models.length }));
      if (!model.trim() && result.models.length > 0) {
        setModel(result.models[0]);
      }
    });

  const persistProvider = async () => {
    await apiFetch<LLMProvider>(`/v1/settings/llm/providers/${provider.id}`, {
      method: "PATCH",
      body: jsonBody({
        name: name.trim(),
        base_url: baseUrl.trim(),
        model: model.trim(),
        api_key: apiKey.trim() || null,
        auth_type: authType,
        auth_header: authHeader.trim() || "Authorization",
        auth_prefix: authPrefix,
      }),
    });
    setApiKey("");
    captureCard({
      name: name.trim(),
      baseUrl: baseUrl.trim(),
      model: model.trim(),
      apiKey: "",
      authType,
      authHeader: authHeader.trim() || "Authorization",
      authPrefix,
    });
    const state = await apiFetch<LLMProvidersState>("/v1/settings/llm/providers");
    onChanged(state);
    onNotice(t("llmSettings.providerSaved", { name: name.trim() }));
  };

  const save = () => run("save", persistProvider);

  useUnsavedGuard(
    `llm-provider-${provider.id}`,
    canEdit && cardDirty,
    canEdit
      ? async () => {
          onError(null);
          try {
            await persistProvider();
          } catch (err) {
            onError(err instanceof Error ? err.message : String(err));
            throw err;
          }
        }
      : undefined,
  );

  const activate = () =>
    run("active", async () => {
      const state = await apiFetch<LLMProvidersState>("/v1/settings/llm/active", {
        method: "PUT",
        body: jsonBody({ provider_id: provider.id }),
      });
      onChanged(state);
      onNotice(t("llmSettings.providerActive", { name: provider.name }));
    });

  const remove = () =>
    run("delete", async () => {
      await apiFetch<{ deleted: boolean; active_id: string | null }>(
        `/v1/settings/llm/providers/${provider.id}`,
        { method: "DELETE" },
      );
      const state = await apiFetch<LLMProvidersState>("/v1/settings/llm/providers");
      onChanged(state);
      onNotice(t("llmSettings.providerDeleted", { name: provider.name }));
    });

  return (
    <Card withBorder>
      <Stack gap="sm">
        <Group justify="space-between" align="center">
          <Group gap="xs">
            <Text fw={600}>{provider.name}</Text>
            {active ? <Badge color="green">{t("llmSettings.activeBadge")}</Badge> : null}
          </Group>
          <Group gap="xs">
            {canEdit ? (
              <Button
                size="compact-sm"
                variant="light"
                onClick={() => void activate()}
                loading={busy === "active"}
                disabled={active}
              >
                {t("llmSettings.makeActive")}
              </Button>
            ) : null}
            {canEdit ? (
              <Button
                size="compact-sm"
                variant="subtle"
                color="red"
                onClick={() => setConfirmDelete(true)}
              >
                {t("common.delete")}
              </Button>
            ) : null}
          </Group>
        </Group>

        <Select
          {...NO_AUTOFILL}
          label={t("llmSettings.preset")}
          description={t("llmSettings.presetHint")}
          placeholder={t("llmSettings.presetNone")}
          data={presetOptions}
          value={preset}
          onChange={applyPreset}
          disabled={!canEdit}
          clearable
        />

        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput
            {...NO_AUTOFILL}
            label={t("llmSettings.providerName")}
            value={name}
            onChange={(event) => setName(event.currentTarget.value)}
            disabled={!canEdit}
          />
          <TextInput
            {...NO_AUTOFILL}
            label="base_url"
            placeholder="http://host.docker.internal:1234/v1"
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.currentTarget.value)}
            disabled={!canEdit}
          />
        </SimpleGrid>

        <Group align="flex-end" gap="sm" wrap="nowrap">
          <Select
            {...NO_AUTOFILL}
            label={t("llmSettings.auth")}
            data={authOptions}
            value={authType}
            onChange={(value) => {
              const nextType = (value as LLMAuthType | null) ?? "bearer";
              setAuthType(nextType);
              if (nextType === "bearer" && !authPrefix.trim()) {
                setAuthPrefix("Bearer ");
              }
            }}
            disabled={!canEdit}
            allowDeselect={false}
            w={190}
          />
          <PasswordInput
            {...NO_AUTOFILL}
            label={t("llmSettings.apiKey")}
            description={
              authType === "none"
                ? t("llmSettings.apiKeyUnset")
                : t("llmSettings.authKeyPreview", {
                    header: authHeader || "Authorization",
                    prefix: authPrefix,
                  })
            }
            leftSection={
              authType === "none" ? undefined : (
                <Text size="xs" c="dimmed">
                  {authPrefix.trim() || "—"}
                </Text>
              )
            }
            leftSectionWidth={authType === "none" ? undefined : 64}
            value={apiKey}
            onChange={(event) => setApiKey(event.currentTarget.value)}
            disabled={!canEdit || authType === "none"}
            autoComplete="new-password"
            style={{ flex: 1, minWidth: 0 }}
          />
        </Group>

        {authType === "header" ? (
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput
              {...NO_AUTOFILL}
              inputWrapperOrder={[...FIELD_ORDER]}
              label={t("llmSettings.authHeader")}
              placeholder="Authorization"
              value={authHeader}
              onChange={(event) => setAuthHeader(event.currentTarget.value)}
              disabled={!canEdit}
            />
            <TextInput
              {...NO_AUTOFILL}
              inputWrapperOrder={[...FIELD_ORDER]}
              label={t("llmSettings.authPrefix")}
              description={t("llmSettings.authPrefixHint")}
              value={authPrefix}
              onChange={(event) => setAuthPrefix(event.currentTarget.value)}
              disabled={!canEdit}
            />
          </SimpleGrid>
        ) : null}

        <Group align="end" gap="sm">
          <Autocomplete
            {...NO_AUTOFILL}
            label={t("llmSettings.model")}
            description={t("llmSettings.modelHint")}
            placeholder={t("llmSettings.modelPlaceholder")}
            data={models}
            value={model}
            onChange={setModel}
            disabled={!canEdit}
            style={{ flex: 1 }}
            maxDropdownHeight={260}
            limit={50}
          />
          <Button variant="default" onClick={() => void loadModels()} loading={busy === "models"}>
            {t("llmSettings.fetchModels")}
          </Button>
        </Group>
        <Group justify="flex-end">
          <Button onClick={() => void save()} loading={busy === "save"} disabled={!canEdit}>
            {t("common.save")}
          </Button>
        </Group>
        <Text size="xs" c="dimmed">
          {provider.updated_at
            ? t("llmSettings.updatedAt", { date: formatDate(provider.updated_at) })
            : ""}
        </Text>
      </Stack>

      <Modal
        opened={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title={t("llmSettings.deleteTitle", { name: provider.name })}
        size="sm"
      >
        <Stack gap="sm">
          <Text size="sm">
            {t("llmSettings.deleteBody")}
            {active ? t("llmSettings.deleteActiveNote") : ""}
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setConfirmDelete(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              color="red"
              loading={busy === "delete"}
              onClick={() => {
                setConfirmDelete(false);
                void remove();
              }}
            >
              {t("common.delete")}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Card>
  );
}

const EMPTY_PROVIDER_DRAFT = {
  name: "",
  base_url: "",
  api_key: "",
  model: "",
  auth_type: "bearer" as LLMAuthType,
  auth_header: "Authorization",
  auth_prefix: "Bearer ",
  preset: null as string | null,
};

export function SettingsPage() {
  const { t } = useTranslation();
  const me = useSession();
  const canEdit = me.user.is_superadmin;

  const [state, setState] = useState<LLMProvidersState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState(EMPTY_PROVIDER_DRAFT);
  const { dirty: addDirty, captureBaseline: captureAdd } = useBaselineDirty(draft, addOpen);
  const [pageSearch, setPageSearch] = useState("");

  const visibleProviders = useMemo(() => {
    const items = state?.items ?? [];
    if (!pageSearch.trim()) {
      return items;
    }
    return items.filter((provider) =>
      matchesPageSearch(pageSearch, [
        provider.name,
        provider.base_url,
        provider.model,
        provider.id,
      ]),
    );
  }, [state?.items, pageSearch]);

  const authOptions = useMemo(
    () =>
      LLM_AUTH_TYPES.map((item) => ({
        value: item.value,
        label: t(`llmSettings.authTypes.${AUTH_I18N_KEY[item.value]}.short`),
      })),
    [t],
  );

  const presetOptions = useMemo(
    () =>
      LLM_PROVIDER_PRESETS.map((item) => ({
        value: item.value,
        label: t(`llmSettings.presets.${PRESET_I18N_KEY[item.value]}.label`),
      })),
    [t],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setState(await apiFetch<LLMProvidersState>("/v1/settings/llm/providers"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const persistCreate = async () => {
    await apiFetch<LLMProvider>("/v1/settings/llm/providers", {
      method: "POST",
      body: jsonBody({
        name: draft.name.trim(),
        base_url: draft.base_url.trim(),
        api_key: draft.api_key.trim() || null,
        model: draft.model.trim(),
        auth_type: draft.auth_type,
        auth_header: draft.auth_header.trim() || "Authorization",
        auth_prefix: draft.auth_prefix,
      }),
    });
    captureAdd(EMPTY_PROVIDER_DRAFT);
    setAddOpen(false);
    setDraft(EMPTY_PROVIDER_DRAFT);
    await load();
    setNotice(t("llmSettings.providerAdded"));
  };

  const handleCreate = async () => {
    setCreating(true);
    setError(null);
    setNotice(null);
    try {
      await persistCreate();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreating(false);
    }
  };

  const openAdd = () => {
    setDraft(EMPTY_PROVIDER_DRAFT);
    captureAdd(EMPTY_PROVIDER_DRAFT);
    setAddOpen(true);
  };

  const closeAdd = () => setAddOpen(false);

  const { requestLeave: requestAddLeave } = useUnsavedGuard(
    "llm-provider-create",
    addOpen && addDirty,
    async () => {
      setError(null);
      try {
        await persistCreate();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        throw err;
      }
    },
  );

  useAssistForm(
    "llm",
    addOpen
      ? {
          page_search: pageSearch,
          name: draft.name,
          base_url: draft.base_url,
          model: draft.model,
          auth_type: draft.auth_type,
          auth_header: draft.auth_header,
          auth_prefix: draft.auth_prefix,
        }
      : {
          page_search: pageSearch,
          providers: (state?.items ?? []).map((p) => ({
            id: p.id,
            name: p.name,
            base_url: p.base_url,
            model: p.model,
          })),
        },
    (fields) => {
      const { page_search: _p, ...rest } = fields;
      const next = { ...draft };
      let touched = false;
      if (typeof rest.name === "string" && rest.name.trim()) {
        next.name = rest.name;
        touched = true;
      }
      if (typeof rest.base_url === "string" && rest.base_url.trim()) {
        next.base_url = rest.base_url;
        touched = true;
      }
      if (typeof rest.model === "string" && rest.model.trim()) {
        next.model = rest.model;
        touched = true;
      }
      if (["bearer", "header", "none"].includes(String(rest.auth_type))) {
        next.auth_type = rest.auth_type as LLMAuthType;
        touched = true;
      }
      if (typeof rest.auth_header === "string" && rest.auth_header.trim()) {
        next.auth_header = rest.auth_header;
        touched = true;
      }
      if (typeof rest.auth_prefix === "string") {
        next.auth_prefix = rest.auth_prefix;
        touched = true;
      }
      if (!touched) {
        return Object.keys(rest).length === 0 ? null : t("llmSettings.noProviderFields");
      }
      if (!addOpen) {
        captureAdd(EMPTY_PROVIDER_DRAFT);
      }
      setDraft(next);
      setAddOpen(true);
      return null;
    },
    (query) => {
      setPageSearch(query);
      return null;
    },
  );

  const effective = state?.effective;
  const sourceLabel =
    effective?.source === "provider"
      ? t("llmSettings.sourceProvider")
      : effective?.source === "db"
        ? t("llmSettings.sourceLegacy")
        : t("llmSettings.sourceEnv");

  return (
    <Stack gap="md">
      <PageHeader title={t("llmSettings.title")}>
        <PageSearch value={pageSearch} onChange={setPageSearch} />
        {canEdit ? <Button onClick={openAdd}>{t("llmSettings.addProvider")}</Button> : null}
      </PageHeader>

      {error ? (
        <Alert color="red" title={t("common.error")}>
          {error}
        </Alert>
      ) : null}
      {notice ? <Alert color="green">{notice}</Alert> : null}
      {!canEdit ? (
        <Alert color="gray" title={t("common.viewOnly")}>
          {t("llmSettings.viewOnlyBody")}
        </Alert>
      ) : null}

      {effective ? (
        <Card withBorder bg="var(--mantine-color-default-hover)">
          <Stack gap={4}>
            <Group gap="sm">
              <Text fw={600}>{t("llmSettings.effectiveEndpoint")}</Text>
              <Badge variant="light" color={effective.source === "provider" ? "green" : "gray"}>
                {sourceLabel}
              </Badge>
            </Group>
            <Text size="sm">
              {effective.base_url || t("common.emptyDash")} ·{" "}
              {effective.model || t("llmSettings.modelUnset")}
              {effective.api_key_set ? t("llmSettings.keySet") : t("llmSettings.keyMissing")}
            </Text>
            <Text size="xs" c="dimmed">
              {t("llmSettings.effectiveHint")}
            </Text>
          </Stack>
        </Card>
      ) : null}

      {loading ? (
        <Group justify="center" py="xl">
          <Loader />
        </Group>
      ) : (
        <Stack gap="md">
          {state && state.items.length === 0 ? (
            <Alert color="gray">{t("llmSettings.empty")}</Alert>
          ) : visibleProviders.length === 0 ? (
            <Alert color="gray">{t("common.emptyPageFilter")}</Alert>
          ) : (
            visibleProviders.map((provider) => (
              <ProviderCard
                key={provider.id}
                provider={provider}
                active={state?.active_id === provider.id}
                canEdit={canEdit}
                onChanged={setState}
                onError={setError}
                onNotice={setNotice}
              />
            ))
          )}
        </Stack>
      )}

      <Modal
        opened={addOpen}
        onClose={() => requestAddLeave(closeAdd)}
        title={t("llmSettings.newProvider")}
      >
        <Stack gap="sm">
          <Select
            {...NO_AUTOFILL}
            id="provider-preset"
            label={t("llmSettings.preset")}
            description={t("llmSettings.presetHintShort")}
            placeholder={t("llmSettings.presetNone")}
            data={presetOptions}
            value={draft.preset}
            onChange={(value) => {
              const found = LLM_PROVIDER_PRESETS.find((item) => item.value === value);
              setDraft((prev) => ({
                ...prev,
                preset: value,
                name:
                  prev.name.trim() ||
                  presetOptions.find((item) => item.value === value)?.label ||
                  prev.name,
                base_url: found?.base_url || prev.base_url,
                auth_type: found?.auth_type ?? prev.auth_type,
                auth_header: found?.auth_header ?? prev.auth_header,
                auth_prefix: found?.auth_prefix ?? prev.auth_prefix,
              }));
            }}
            clearable
          />
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput
              {...NO_AUTOFILL}
              id="provider-name"
              label={t("llmSettings.providerName")}
              placeholder={t("llmSettings.providerNamePlaceholder")}
              value={draft.name}
              onChange={(event) => {
                const value = event.currentTarget.value;
                setDraft((prev) => ({ ...prev, name: value }));
              }}
              required
            />
            <TextInput
              {...NO_AUTOFILL}
              id="provider-base-url"
              label="base_url"
              placeholder="http://host.docker.internal:1234/v1"
              value={draft.base_url}
              onChange={(event) => {
                const value = event.currentTarget.value;
                setDraft((prev) => ({ ...prev, base_url: value }));
              }}
              required
            />
          </SimpleGrid>
          <Group align="flex-end" gap="sm" wrap="nowrap">
            <Select
              {...NO_AUTOFILL}
              id="provider-auth-type"
              label={t("llmSettings.auth")}
              data={authOptions}
              value={draft.auth_type}
              onChange={(value) => {
                const nextType = (value as LLMAuthType | null) ?? "bearer";
                setDraft((prev) => ({
                  ...prev,
                  auth_type: nextType,
                  auth_prefix:
                    nextType === "bearer" && !prev.auth_prefix.trim()
                      ? "Bearer "
                      : prev.auth_prefix,
                }));
              }}
              allowDeselect={false}
              w={190}
            />
            <PasswordInput
              {...NO_AUTOFILL}
              id="provider-api-key"
              label={t("llmSettings.apiKey")}
              description={
                draft.auth_type === "none"
                  ? t("llmSettings.apiKeyHintLocal")
                  : t("llmSettings.authKeyPreview", {
                      header: draft.auth_header || "Authorization",
                      prefix: draft.auth_prefix,
                    })
              }
              leftSection={
                draft.auth_type === "none" ? undefined : (
                  <Text size="xs" c="dimmed">
                    {draft.auth_prefix.trim() || "—"}
                  </Text>
                )
              }
              leftSectionWidth={draft.auth_type === "none" ? undefined : 64}
              value={draft.api_key}
              onChange={(event) => {
                const value = event.currentTarget.value;
                setDraft((prev) => ({ ...prev, api_key: value }));
              }}
              disabled={draft.auth_type === "none"}
              autoComplete="new-password"
              style={{ flex: 1, minWidth: 0 }}
            />
          </Group>
          {draft.auth_type === "header" ? (
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <TextInput
                {...NO_AUTOFILL}
                inputWrapperOrder={[...FIELD_ORDER]}
                id="provider-auth-header"
                label={t("llmSettings.authHeader")}
                placeholder="Authorization"
                value={draft.auth_header}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  setDraft((prev) => ({ ...prev, auth_header: value }));
                }}
              />
              <TextInput
                {...NO_AUTOFILL}
                inputWrapperOrder={[...FIELD_ORDER]}
                id="provider-auth-prefix"
                label={t("llmSettings.authPrefix")}
                description={t("llmSettings.authPrefixHint")}
                placeholder="Bearer "
                value={draft.auth_prefix}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  setDraft((prev) => ({ ...prev, auth_prefix: value }));
                }}
              />
            </SimpleGrid>
          ) : null}
          <TextInput
            {...NO_AUTOFILL}
            id="provider-model"
            label={t("llmSettings.model")}
            description={t("llmSettings.modelHintCreate")}
            value={draft.model}
            onChange={(event) => {
              const value = event.currentTarget.value;
              setDraft((prev) => ({ ...prev, model: value }));
            }}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={() => requestAddLeave(closeAdd)}>
              {t("common.cancel")}
            </Button>
            <Button
              onClick={() => void handleCreate()}
              loading={creating}
              disabled={!draft.name.trim() || !draft.base_url.trim()}
            >
              {t("common.add")}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
