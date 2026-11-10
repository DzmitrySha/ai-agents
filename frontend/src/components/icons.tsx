import type { ReactNode } from "react";

/** Набор инлайн-иконок 16×16 (stroke = currentColor) — без внешних зависимостей. */
function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      width={16}
      height={16}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export function AgentsIcon() {
  return (
    <Icon>
      <rect x="4" y="7" width="16" height="12" rx="3" />
      <path d="M12 7V4" />
      <circle cx="9" cy="13" r="1.2" fill="currentColor" stroke="none" />
      <circle cx="15" cy="13" r="1.2" fill="currentColor" stroke="none" />
      <path d="M9.5 16.5h5" />
    </Icon>
  );
}

export function RunsIcon() {
  return (
    <Icon>
      <path d="M3 12h3l2.5-6 3.5 12 2.5-6h6" />
    </Icon>
  );
}

export function ToolsIcon() {
  return (
    <Icon>
      <path d="M14.5 5.5a3.6 3.6 0 0 0 4.6 4.6L9.4 19.8a2.2 2.2 0 0 1-3.1-3.1z" />
      <path d="M6.5 17.5h.01" />
    </Icon>
  );
}

export function SkillsIcon() {
  return (
    <Icon>
      <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z" />
      <path d="M8 7h8M8 11h6" />
    </Icon>
  );
}

export function McpIcon() {
  return (
    <Icon>
      <path d="M9 3v5M15 3v5" />
      <path d="M6 8h12v3a6 6 0 0 1-6 6 6 6 0 0 1-6-6z" />
      <path d="M12 17v4" />
    </Icon>
  );
}

export function OverviewIcon() {
  return (
    <Icon>
      <path d="M4 20V9M10 20V4M16 20v-7M22 20H2" />
    </Icon>
  );
}

export function UsersIcon() {
  return (
    <Icon>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3 20a6 6 0 0 1 12 0" />
      <path d="M16 6.2a3 3 0 0 1 0 5.6M17.5 20a5.5 5.5 0 0 0-2-4.3" />
    </Icon>
  );
}

export function LlmIcon() {
  return (
    <Icon>
      <path d="M12 3l1.8 4.6L18.5 9.5 13.8 11.3 12 16l-1.8-4.7L5.5 9.5l4.7-1.9z" />
      <path d="M18.5 16.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" />
    </Icon>
  );
}

export function KeysIcon() {
  return (
    <Icon>
      <circle cx="8" cy="8" r="4" />
      <path d="M11 11l9 9M17 17l2-2M14.5 14.5l2-2" />
    </Icon>
  );
}

export function DoctorIcon() {
  return (
    <Icon>
      <path d="M3 12h4l2.5-6 4 12 2.5-6H21" />
    </Icon>
  );
}

export function SchedulesIcon() {
  return (
    <Icon>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </Icon>
  );
}

export function NotificationsIcon() {
  return (
    <Icon>
      <path d="M6 9a6 6 0 0 1 12 0v5l2 2H4l2-2z" />
      <path d="M10 19a2 2 0 0 0 4 0" />
    </Icon>
  );
}

export function PacksIcon() {
  return (
    <Icon>
      <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z" />
      <path d="M4 7.5l8 4.5 8-4.5M12 12v9" />
    </Icon>
  );
}

export function ChevronDownIcon() {
  return (
    <Icon>
      <path d="M6 9l6 6 6-6" />
    </Icon>
  );
}

export function DocsIcon() {
  return (
    <Icon>
      <path d="M6 4h9l3 3v13H6z" />
      <path d="M15 4v3h3M8 11h8M8 15h6" />
    </Icon>
  );
}

export function AboutIcon() {
  return (
    <Icon>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 10v6M12 7.5h.01" />
    </Icon>
  );
}

export function SettingsIcon() {
  return (
    <Icon>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3v2.2M12 18.8V21M4.9 6.5l1.6 1.6M17.5 17.9l1.6 1.6M3 12h2.2M18.8 12H21M4.9 17.5l1.6-1.6M17.5 6.1l1.6-1.6" />
    </Icon>
  );
}

export const NAV_ICONS: Record<string, ReactNode> = {
  "/agents": <AgentsIcon />,
  "/runs": <RunsIcon />,
  "/schedules": <SchedulesIcon />,
  "/tools": <ToolsIcon />,
  "/skills": <SkillsIcon />,
  "/integrations/mcp": <McpIcon />,
  "/stats": <OverviewIcon />,
  "/admin/users": <UsersIcon />,
  "/admin/doctor": <DoctorIcon />,
  "/admin/notifications": <NotificationsIcon />,
  "/admin/packs": <PacksIcon />,
  "/admin/llm": <LlmIcon />,
  "/admin/keys": <KeysIcon />,
  "/docs": <DocsIcon />,
  "/about": <AboutIcon />,
  "/settings": <SettingsIcon />,
};

export function PlusIcon() {
  return (
    <Icon>
      <path d="M12 5v14M5 12h14" />
    </Icon>
  );
}

export function CardsViewIcon() {
  return (
    <Icon>
      <rect x="3" y="3" width="8" height="8" rx="2" />
      <rect x="13" y="3" width="8" height="8" rx="2" />
      <rect x="3" y="13" width="8" height="8" rx="2" />
      <rect x="13" y="13" width="8" height="8" rx="2" />
    </Icon>
  );
}

export function TableViewIcon() {
  return (
    <Icon>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 9h18M3 14h18M9 9v11M15 9v11" />
    </Icon>
  );
}

export function EditIcon() {
  return (
    <Icon>
      <path d="M4 20h4l10-10a2.5 2.5 0 0 0-3.5-3.5L4 16.5z" />
      <path d="M13.5 6.5l4 4" />
    </Icon>
  );
}

export function TrashIcon() {
  return (
    <Icon>
      <path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13" />
      <path d="M10 11v5M14 11v5" />
    </Icon>
  );
}

export function PlayIcon() {
  return (
    <Icon>
      <path d="M7 4.5v15l12-7.5z" />
    </Icon>
  );
}

export function OpenIcon() {
  return (
    <Icon>
      <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z" />
      <circle cx="12" cy="12" r="2.6" />
    </Icon>
  );
}

export function RefreshIcon() {
  return (
    <Icon>
      <path d="M20 11a8 8 0 1 0-2.3 5.7" />
      <path d="M20 5v6h-6" />
    </Icon>
  );
}

export function CheckIcon() {
  return (
    <Icon>
      <path d="M5 12.5l4.5 4.5L19 7" />
    </Icon>
  );
}

export function PowerIcon() {
  return (
    <Icon>
      <path d="M12 3v8" />
      <path d="M7.5 6.5a7 7 0 1 0 9 0" />
    </Icon>
  );
}

export function SchemaIcon() {
  return (
    <Icon>
      <path d="M8 4c-2 0-3 1-3 3v2c0 1.5-1 2-2 2 1 0 2 .5 2 2v2c0 2 1 3 3 3" />
      <path d="M16 4c2 0 3 1 3 3v2c0 1.5 1 2 2 2-1 0-2 .5-2 2v2c0 2-1 3-3 3" />
    </Icon>
  );
}

export function SearchIcon() {
  return (
    <Icon>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M16 16l4.5 4.5" />
    </Icon>
  );
}

export function CopyIcon() {
  return (
    <Icon>
      <rect x="9" y="9" width="11" height="11" rx="2" />
      <path d="M15 5H6a2 2 0 0 0-2 2v9" />
    </Icon>
  );
}
