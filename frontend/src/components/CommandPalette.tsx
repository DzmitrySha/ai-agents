import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Badge,
  Box,
  Group,
  Modal,
  ScrollArea,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { apiFetch, asItems } from "../api";
import type { AgentList, RunList, ToolSpec } from "../types";

type PaletteGroup = "sections" | "agents" | "tools" | "recentRuns";

interface PaletteItem {
  id: string;
  group: PaletteGroup;
  label: string;
  hint: string;
  to: string;
}

interface CommandPaletteProps {
  opened: boolean;
  onClose: () => void;
  nav: { label: string; to: string }[];
}

const MAX_PER_GROUP = 6;

/** Быстрый переход: Ctrl/⌘+K → разделы, агенты, инструменты, последние запуски. */
export function CommandPalette({ opened, onClose, nav }: CommandPaletteProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [agents, setAgents] = useState<PaletteItem[]>([]);
  const [tools, setTools] = useState<PaletteItem[]>([]);
  const [runs, setRuns] = useState<PaletteItem[]>([]);
  const [active, setActive] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    const [agentsData, toolsData, runsData] = await Promise.allSettled([
      apiFetch<AgentList>("/v1/agents?scope=all&limit=100"),
      apiFetch<ToolSpec[]>("/v1/tools"),
      apiFetch<RunList>("/v1/runs?limit=10"),
    ]);
    if (agentsData.status === "fulfilled") {
      setAgents(
        asItems(agentsData.value).map((agent) => ({
          id: `agent-${agent.id}`,
          group: "agents" as const,
          label: agent.name || agent.slug,
          hint: `${agent.slug} · ${agent.status}`,
          to: `/agents/${encodeURIComponent(agent.slug)}`,
        })),
      );
    }
    if (toolsData.status === "fulfilled") {
      setTools(
        asItems(toolsData.value).map((tool) => ({
          id: `tool-${tool.name}`,
          group: "tools" as const,
          label: tool.name,
          hint:
            tool.source === "custom"
              ? t("commandPalette.toolHintCustom")
              : t("commandPalette.toolHintBuiltin"),
          to: "/tools",
        })),
      );
    }
    if (runsData.status === "fulfilled") {
      setRuns(
        asItems(runsData.value).map((run) => ({
          id: `run-${run.run_id}`,
          group: "recentRuns" as const,
          label: run.agent_id || run.run_id,
          hint: `${run.status} · ${run.run_id.slice(0, 8)}`,
          to: `/runs/${encodeURIComponent(run.run_id)}`,
        })),
      );
    }
    setLoaded(true);
  }, [t]);

  useEffect(() => {
    setLoaded(false);
  }, [i18n.language]);

  useEffect(() => {
    if (opened && !loaded) {
      void load();
    }
    if (!opened) {
      setQuery("");
      setActive(0);
    }
  }, [opened, loaded, load]);

  useEffect(() => {
    if (opened) {
      window.setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [opened]);

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const sections: PaletteItem[][] = [
      nav.map((item) => ({
        id: `nav-${item.to}`,
        group: "sections" as const,
        label: item.label,
        hint: item.to,
        to: item.to,
      })),
      agents,
      tools,
      runs,
    ];
    return sections
      .map((items) =>
        items.filter(
          (item) =>
            !needle ||
            item.label.toLowerCase().includes(needle) ||
            item.hint.toLowerCase().includes(needle),
        ),
      )
      .flatMap((items) => items.slice(0, MAX_PER_GROUP));
  }, [query, nav, agents, tools, runs]);

  useEffect(() => {
    setActive(0);
  }, [query]);

  const go = (item: PaletteItem | undefined) => {
    if (!item) {
      return;
    }
    navigate(item.to);
    onClose();
  };

  const grouped: { group: PaletteGroup; items: PaletteItem[] }[] = [];
  for (const item of results) {
    const bucket = grouped.find((entry) => entry.group === item.group);
    if (bucket) {
      bucket.items.push(item);
    } else {
      grouped.push({ group: item.group, items: [item] });
    }
  }

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      withCloseButton={false}
      size="lg"
      padding={0}
      yOffset="12vh"
      overlayProps={{ backgroundOpacity: 0.35 }}
    >
      <Box p="sm">
        <TextInput
          ref={inputRef}
          autoComplete="off"
          spellCheck={false}
          placeholder={t("commandPalette.placeholder")}
          value={query}
          onChange={(event) => setQuery(event.currentTarget.value)}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setActive((prev) => Math.min(prev + 1, results.length - 1));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setActive((prev) => Math.max(prev - 1, 0));
            } else if (event.key === "Enter") {
              event.preventDefault();
              go(results[active]);
            }
          }}
          size="md"
          variant="filled"
        />
      </Box>

      <ScrollArea h={380} px="xs" pb="xs">
        {results.length === 0 ? (
          <Text size="sm" c="dimmed" p="md">
            {loaded ? t("commandPalette.empty") : t("commandPalette.loading")}
          </Text>
        ) : (
          <Stack gap={4}>
            {grouped.map((bucket) => (
              <Box key={bucket.group}>
                <Text size="xs" c="dimmed" tt="uppercase" fw={600} px="sm" pt="xs">
                  {t(`commandPalette.groups.${bucket.group}`)}
                </Text>
                {bucket.items.map((item) => {
                  const index = results.indexOf(item);
                  const selected = index === active;
                  return (
                    <Group
                      key={item.id}
                      justify="space-between"
                      wrap="nowrap"
                      px="sm"
                      py={6}
                      style={{
                        borderRadius: 6,
                        cursor: "pointer",
                        background: selected ? "var(--mantine-color-default-hover)" : undefined,
                      }}
                      onMouseEnter={() => setActive(index)}
                      onClick={() => go(item)}
                      role="button"
                      tabIndex={-1}
                    >
                      <Text size="sm" truncate>
                        {item.label}
                      </Text>
                      <Text size="xs" c="dimmed" truncate>
                        {item.hint}
                      </Text>
                    </Group>
                  );
                })}
              </Box>
            ))}
          </Stack>
        )}
      </ScrollArea>

      <Group justify="space-between" px="sm" py="xs">
        <Text size="xs" c="dimmed">
          {t("commandPalette.footer")}
        </Text>
        <Badge size="xs" variant="light">
          Ctrl+K
        </Badge>
      </Group>
    </Modal>
  );
}
