import { type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ActionIcon, Badge, Group, TextInput, Title, Tooltip } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { NO_AUTOFILL } from "../formAttrs";
import {
  CardsViewIcon,
  CopyIcon,
  EditIcon,
  KeysIcon,
  OpenIcon,
  PlayIcon,
  PowerIcon,
  RefreshIcon,
  SchemaIcon,
  TableViewIcon,
  TrashIcon,
} from "./icons";

export type ViewMode = "cards" | "table";

const PREFIX = "ai-agents.view.";

export function readViewMode(section: string, fallback: ViewMode = "cards"): ViewMode {
  try {
    const stored = window.localStorage.getItem(`${PREFIX}${section}`);
    return stored === "cards" || stored === "table" ? stored : fallback;
  } catch {
    return fallback;
  }
}

export function saveViewMode(section: string, value: ViewMode): void {
  try {
    window.localStorage.setItem(`${PREFIX}${section}`, value);
  } catch {
    // localStorage недоступен — вид не запоминаем
  }
}

/** Единый заголовок раздела: слева название и счётчик, справа — вид, действия, «Добавить». */
export function PageHeader({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children?: ReactNode;
}) {
  return (
    <Group justify="space-between" align="center" wrap="wrap">
      <Group gap="sm" wrap="nowrap">
        <Title order={2}>{title}</Title>
        {typeof count === "number" ? (
          <Badge variant="light" color="gray">
            {count}
          </Badge>
        ) : null}
      </Group>
      <Group gap="xs" wrap="wrap" justify="flex-end" style={{ flex: "1 1 auto", minWidth: 0 }}>
        {children}
      </Group>
    </Group>
  );
}

/** Единое поле «Поиск на странице» для всех разделов: первым в `PageHeader`, без подписи. */
export function PageSearch({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <TextInput
      {...NO_AUTOFILL}
      aria-label={t("common.search")}
      placeholder={t("common.pageSearchPlaceholder")}
      value={value}
      onChange={(event) => onChange(event.currentTarget.value)}
      w={{ base: "100%", sm: 280 }}
      style={{ flex: "1 1 200px", minWidth: 180, maxWidth: 360 }}
    />
  );
}

/** Переключатель «плашки / таблица»: только иконки, состояние в localStorage. */
export function ViewToggle({
  value,
  onChange,
}: {
  value: ViewMode;
  onChange: (value: ViewMode) => void;
}) {
  const { t } = useTranslation();
  return (
    <Group gap={4} wrap="nowrap">
      {(
        [
          { mode: "cards" as ViewMode, label: t("viewToggle.cards"), icon: <CardsViewIcon /> },
          { mode: "table" as ViewMode, label: t("viewToggle.table"), icon: <TableViewIcon /> },
        ]
      ).map((option) => (
        <Tooltip key={option.mode} label={option.label} withArrow openDelay={200}>
          <ActionIcon
            aria-label={option.label}
            aria-pressed={value === option.mode}
            variant={value === option.mode ? "filled" : "default"}
            size="lg"
            onClick={() => onChange(option.mode)}
          >
            {option.icon}
          </ActionIcon>
        </Tooltip>
      ))}
    </Group>
  );
}

const ACTION_COLORS = {
  edit: "blue",
  delete: "red",
  test: "teal",
  open: "gray",
  key: "yellow",
  toggle: "green",
  schema: "grape",
  refresh: "gray",
  copy: "gray",
} as const;

export type ActionKind = keyof typeof ACTION_COLORS;

const ACTION_ICONS: Record<ActionKind, ReactNode> = {
  edit: <EditIcon />,
  delete: <TrashIcon />,
  test: <PlayIcon />,
  open: <OpenIcon />,
  key: <KeysIcon />,
  toggle: <PowerIcon />,
  schema: <SchemaIcon />,
  refresh: <RefreshIcon />,
  copy: <CopyIcon />,
};

/**
 * Иконочное действие. `variant="light"` даёт тонированный фон, поэтому иконки
 * читаемы и в светлой, и в тёмной, и в portracker-теме.
 */
export function IconAction({
  kind,
  label,
  onClick,
  disabled,
  loading,
}: {
  kind: ActionKind;
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  loading?: boolean;
}) {
  return (
    <Tooltip label={label} withArrow openDelay={200}>
      <ActionIcon
        aria-label={label}
        variant="light"
        color={ACTION_COLORS[kind]}
        size="lg"
        disabled={disabled}
        loading={loading}
        onClick={onClick}
      >
        {ACTION_ICONS[kind]}
      </ActionIcon>
    </Tooltip>
  );
}

/** То же действие, но переход по ссылке (например, в редактор агента). */
export function IconLink({
  kind,
  label,
  to,
}: {
  kind: ActionKind;
  label: string;
  to: string;
}) {
  return (
    <Tooltip label={label} withArrow openDelay={200}>
      <ActionIcon
        aria-label={label}
        variant="light"
        color={ACTION_COLORS[kind]}
        size="lg"
        component={Link}
        to={to}
      >
        {ACTION_ICONS[kind]}
      </ActionIcon>
    </Tooltip>
  );
}
