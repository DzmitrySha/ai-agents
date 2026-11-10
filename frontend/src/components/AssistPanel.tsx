import { useEffect, useMemo, useState } from "react";
import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
  Drawer,
  Group,
  Loader,
  ScrollArea,
  SegmentedControl,
  Stack,
  Text,
  Textarea,
  Tooltip,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { apiFetch, jsonBody } from "../api";
import { NO_AUTOFILL } from "../formAttrs";
import { type AssistMode, useAssist } from "../assist";
import { TrashIcon } from "./icons";
import { useUnsavedGuard } from "../unsavedChanges";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  warnings?: string[];
  fields?: Record<string, unknown> | null;
}

interface ChatResponse {
  answer: string;
  fields: Record<string, unknown> | null;
  warnings: string[];
}

const MODE_VALUES: AssistMode[] = ["form", "advice", "review", "test"];

export function AssistPanel() {
  const { t } = useTranslation();
  const {
    form,
    opened,
    setOpened,
    draftMessage,
    setDraftMessage,
    preferredMode,
    setPreferredMode,
  } = useAssist();
  const [mode, setMode] = useState<AssistMode>("advice");
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!opened) {
      return;
    }
    if (draftMessage) {
      setMessage(draftMessage);
      setDraftMessage("");
    }
    if (preferredMode) {
      setMode(preferredMode);
      setPreferredMode(null);
    }
  }, [opened, draftMessage, preferredMode, setDraftMessage, setPreferredMode]);

  const target = form?.target ?? "general";
  const canFill = mode === "form" && form !== null;
  const draftDirty = opened && message.trim().length > 0;
  const { requestLeave } = useUnsavedGuard("assist-panel", draftDirty);

  const modes = useMemo(
    () =>
      MODE_VALUES.map((value) => ({
        value,
        label: t(`assist.modes.${value}.label`),
        hint: t(`assist.modes.${value}.hint`),
      })),
    [t],
  );

  const closePanel = () => {
    setOpened(false);
    setMessage("");
  };

  const clearHistory = () => {
    setMessages([]);
    setError(null);
    setNotice(null);
  };

  const send = async () => {
    const text = message.trim();
    if (!text || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    const history = messages.slice(-8).map((item) => ({
      role: item.role,
      content: item.content,
    }));
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setMessage("");
    try {
      const response = await apiFetch<ChatResponse>("/v1/assist/chat", {
        method: "POST",
        body: jsonBody({
          mode,
          target,
          message: text,
          current: form?.current ?? {},
          history,
        }),
      });
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: response.answer,
          warnings: response.warnings,
          fields: response.fields,
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const applyFields = (fields: Record<string, unknown>) => {
    if (form === null) {
      return;
    }
    const rest = { ...fields };
    const rawSearch = rest.page_search;
    delete rest.page_search;
    let searchApplied = false;
    if (typeof rawSearch === "string" && rawSearch.trim() && form.applyPageSearch) {
      const err = form.applyPageSearch(rawSearch.trim());
      if (err) {
        setError(err);
        return;
      }
      searchApplied = true;
    }
    if (Object.keys(rest).length === 0) {
      setNotice(
        searchApplied ? t("assist.pageSearchApplied") : t("assist.appliedNotice"),
      );
      return;
    }
    const problem = form.apply(rest);
    if (problem) {
      if (searchApplied) {
        setNotice(t("assist.unexpectedFields"));
        return;
      }
      setError(problem);
      return;
    }
    setNotice(
      searchApplied ? t("assist.pageSearchAndFieldsApplied") : t("assist.appliedNotice"),
    );
  };

  const targetLabel = t(`assist.targets.${target}`, { defaultValue: target });

  return (
    <>
      <Tooltip label={t("assist.title")} position="left">
        <ActionIcon
          size="xl"
          radius="xl"
          variant="filled"
          aria-label={t("assist.ariaLabel")}
          onClick={() => setOpened(true)}
          style={{ position: "fixed", right: 24, bottom: 24, zIndex: 200 }}
        >
          AI
        </ActionIcon>
      </Tooltip>

      <Drawer
        opened={opened}
        onClose={() => requestLeave(closePanel)}
        position="right"
        size={460}
        title={t("assist.title")}
        padding="md"
      >
        <Stack gap="sm" h="100%">
          <Text size="xs" c="dimmed">
            {t("assist.modelHint", { target: targetLabel })}
          </Text>

          <SegmentedControl
            fullWidth
            size="xs"
            value={mode}
            onChange={(value) => setMode(value as AssistMode)}
            data={modes.map((item) => ({ value: item.value, label: item.label }))}
          />
          <Text size="xs" c="dimmed">
            {modes.find((item) => item.value === mode)?.hint}
            {mode === "form" && form === null ? t("assist.formRequired") : ""}
          </Text>

          {error ? (
            <Alert color="red" variant="light" withCloseButton onClose={() => setError(null)}>
              {error}
            </Alert>
          ) : null}
          {notice ? (
            <Alert color="green" variant="light" withCloseButton onClose={() => setNotice(null)}>
              {notice}
            </Alert>
          ) : null}

          <ScrollArea style={{ flex: 1 }} offsetScrollbars>
            <Stack gap="xs">
              {messages.length === 0 ? (
                <Text size="sm" c="dimmed">
                  {t("assist.emptyHint")}
                </Text>
              ) : null}
              {messages.map((item, index) => (
                <Box
                  key={`${item.role}-${index}`}
                  p="xs"
                  style={{
                    borderRadius: 8,
                    background:
                      item.role === "user"
                        ? "var(--mantine-color-default-hover)"
                        : "var(--mantine-color-body)",
                    border: "1px solid var(--mantine-color-default-border)",
                  }}
                >
                  <Text size="xs" c="dimmed" mb={4}>
                    {item.role === "user" ? t("assist.you") : t("assist.assistant")}
                  </Text>
                  <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
                    {item.content}
                  </Text>
                  {item.warnings?.length ? (
                    <Stack gap={2} mt={6}>
                      {item.warnings.map((warning) => (
                        <Text key={warning} size="xs" c="orange">
                          • {warning}
                        </Text>
                      ))}
                    </Stack>
                  ) : null}
                  {item.fields && Object.keys(item.fields).length > 0 ? (
                    <Group gap="xs" mt={6}>
                      <Badge size="xs" variant="light">
                        {t("assist.fieldsCount", { count: Object.keys(item.fields).length })}
                      </Badge>
                      <Button
                        size="compact-xs"
                        variant="light"
                        onClick={() => applyFields(item.fields as Record<string, unknown>)}
                        disabled={form === null}
                      >
                        {t("assist.applyToForm")}
                      </Button>
                    </Group>
                  ) : null}
                </Box>
              ))}
              {busy ? (
                <Group gap="xs">
                  <Loader size="xs" />
                  <Text size="xs" c="dimmed">
                    {t("assist.thinking")}
                  </Text>
                </Group>
              ) : null}
            </Stack>
          </ScrollArea>

          <Textarea
            {...NO_AUTOFILL}
            placeholder={canFill ? t("assist.placeholderForm") : t("assist.placeholderAsk")}
            value={message}
            onChange={(event) => setMessage(event.currentTarget.value)}
            autosize
            minRows={2}
            maxRows={6}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send();
              }
            }}
          />
          <Group justify="space-between">
            <Text size="xs" c="dimmed">
              {t("assist.enterHint")}
            </Text>
            <Group gap="xs">
              <Tooltip label={t("assist.clearHistory")}>
                <ActionIcon
                  variant="default"
                  aria-label={t("assist.clearHistory")}
                  onClick={clearHistory}
                  disabled={messages.length === 0 || busy}
                >
                  <TrashIcon />
                </ActionIcon>
              </Tooltip>
              <Button onClick={() => void send()} loading={busy} disabled={!message.trim()}>
                {t("assist.ask")}
              </Button>
            </Group>
          </Group>
        </Stack>
      </Drawer>
    </>
  );
}
