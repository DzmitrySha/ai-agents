import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { Link, Outlet, useLocation, useOutletContext } from "react-router-dom";
import {
  AppShell,
  Avatar,
  Badge,
  Box,
  Collapse,
  Divider,
  Group,
  Menu,
  NavLink,
  ScrollArea,
  Text,
  Title,
  UnstyledButton,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { apiFetch, asItems, buildQuery, logout } from "../api";
import { AssistProvider } from "../assist";
import { CommandPalette } from "./CommandPalette";
import { ChevronDownIcon, NAV_ICONS } from "./icons";
import { AssistPanel } from "./AssistPanel";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { ThemeSwitcher } from "./ThemeSwitcher";
import type { Me } from "../types";

interface LayoutOutlet {
  me: Me;
}

export function useSession(): Me {
  return useOutletContext<LayoutOutlet>().me;
}

interface NavItem {
  label: string;
  to: string;
  superadminOnly?: boolean;
  writeOnly?: boolean;
}

interface NavItemDef {
  labelKey: string;
  to: string;
  superadminOnly?: boolean;
  writeOnly?: boolean;
}

const RUNS_SEEN_KEY = "ai-agents.runs-seen-at";
const NAV_OPEN_KEY = "ai-agents.nav-open";

interface NavCounts {
  drafts: number;
  failedRuns: number;
  disabledMcp: number;
}

interface NavGroup {
  title?: string;
  items: NavItem[];
}

interface NavGroupDef {
  titleKey: string;
  items: NavItemDef[];
}

/** Группы навбара — ключи переводов; подписи через t(). */
const NAV_GROUPS: NavGroupDef[] = [
  {
    titleKey: "nav.groups.work",
    items: [
      { labelKey: "nav.items.agents", to: "/agents" },
      { labelKey: "nav.items.tools", to: "/tools", writeOnly: true },
      { labelKey: "nav.items.skills", to: "/skills", writeOnly: true },
      // Пункт «Плагины» (/admin/packs) скрыт: страница и API остаются,
      // в навигацию вернуть — добавить строку nav.items.packs обратно.
    ],
  },
  {
    titleKey: "nav.groups.integrations",
    items: [
      { labelKey: "nav.items.mcp", to: "/integrations/mcp", writeOnly: true },
      { labelKey: "nav.items.serviceKeys", to: "/admin/keys", superadminOnly: true },
      { labelKey: "nav.items.llmProviders", to: "/admin/llm", superadminOnly: true },
    ],
  },
  {
    titleKey: "nav.groups.administration",
    items: [
      { labelKey: "nav.items.users", to: "/admin/users", superadminOnly: true },
      { labelKey: "nav.items.notifications", to: "/admin/notifications", superadminOnly: true },
      { labelKey: "nav.items.schedules", to: "/schedules" },
      { labelKey: "nav.items.settings", to: "/settings" },
    ],
  },
  {
    titleKey: "nav.groups.analytics",
    items: [
      { labelKey: "nav.items.overview", to: "/stats" },
      { labelKey: "nav.items.runs", to: "/runs" },
      { labelKey: "nav.items.doctor", to: "/admin/doctor", superadminOnly: true },
    ],
  },
  {
    titleKey: "nav.groups.help",
    items: [
      { labelKey: "nav.items.docs", to: "/docs" },
      { labelKey: "nav.items.about", to: "/about" },
    ],
  },
];

/** superadmin | admin | user; старые сессии без app_role считаем пользователем. */
export function roleOf(me: Me): "superadmin" | "admin" | "user" {
  if (me.user.is_superadmin) {
    return "superadmin";
  }
  return me.user.app_role ?? "user";
}

/** superadmin — фиолетовый (не красный: красный в UI = ошибка), admin — синий, user — зелёный. */
const ROLE_COLOR: Record<"superadmin" | "admin" | "user", string> = {
  superadmin: "grape",
  admin: "blue",
  user: "green",
};

function isActive(pathname: string, to: string): boolean {
  return pathname === to || pathname.startsWith(`${to}/`);
}

function readNavOpen(): Record<string, boolean> {
  try {
    const raw = window.localStorage.getItem(NAV_OPEN_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function visibleItems(items: NavItemDef[], role: "superadmin" | "admin" | "user"): NavItemDef[] {
  return items.filter(
    (item) =>
      (!item.superadminOnly || role === "superadmin") &&
      (!item.writeOnly || role !== "user"),
  );
}

export function AppLayout({ me }: { me: Me }) {
  const { t } = useTranslation();
  const location = useLocation();
  const [busy, setBusy] = useState(false);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(readNavOpen);

  const handleLogout = async () => {
    setBusy(true);
    try {
      await logout();
    } catch {
      // сессия могла уже истечь — всё равно уходим на логин
    } finally {
      window.location.assign("/login");
    }
  };

  const [counts, setCounts] = useState<NavCounts>({ drafts: 0, failedRuns: 0, disabledMcp: 0 });
  const [paletteOpen, setPaletteOpen] = useState(false);

  const loadCounts = useCallback(async () => {
    const [agents, runs, connections] = await Promise.allSettled([
      apiFetch<{ items?: { status: string }[] } | { status: string }[]>(
        `/v1/agents${buildQuery({ scope: "all", limit: 200 })}`,
      ),
      apiFetch<{ items?: { created_at: string }[] }>(
        `/v1/runs${buildQuery({ status: "failed", limit: 50 })}`,
      ),
      apiFetch<{ items?: { enabled: boolean }[] } | { enabled: boolean }[]>(
        "/v1/mcp-connections",
      ),
    ]);
    const seenAt = window.localStorage.getItem(RUNS_SEEN_KEY) ?? "";
    setCounts({
      drafts:
        agents.status === "fulfilled"
          ? asItems(agents.value).filter((agent) => agent.status === "draft").length
          : 0,
      failedRuns:
        runs.status === "fulfilled"
          ? asItems(runs.value).filter((run) => String(run.created_at ?? "") > seenAt).length
          : 0,
      disabledMcp:
        connections.status === "fulfilled"
          ? asItems(connections.value).filter((conn) => !conn.enabled).length
          : 0,
    });
  }, []);

  useEffect(() => {
    void loadCounts();
    const timer = window.setInterval(() => void loadCounts(), 60_000);
    return () => window.clearInterval(timer);
  }, [loadCounts]);

  // Открыл «Запуски» — ошибки считаются просмотренными, бейдж гаснет.
  useEffect(() => {
    if (!location.pathname.startsWith("/runs")) {
      return;
    }
    window.localStorage.setItem(RUNS_SEEN_KEY, new Date().toISOString());
    setCounts((prev) => (prev.failedRuns === 0 ? prev : { ...prev, failedRuns: 0 }));
  }, [location.pathname]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const role = roleOf(me);
  // ФИО из Keycloak; email — только фолбэк.
  const userLabel = me.user.name || me.user.email || me.user.id;

  const navGroups: NavGroup[] = useMemo(
    () =>
      NAV_GROUPS.map((group) => ({
        title: t(group.titleKey),
        items: visibleItems(group.items, role).map((item) => ({
          label: t(item.labelKey),
          to: item.to,
          superadminOnly: item.superadminOnly,
          writeOnly: item.writeOnly,
        })),
      })).filter((group) => group.items.length > 0),
    [role, t],
  );

  const navCounts: Record<string, number> = {
    "/agents": counts.drafts,
    "/runs": counts.failedRuns,
    "/integrations/mcp": counts.disabledMcp,
  };
  const navBadgeTitles: Record<string, string> = {
    "/agents": t("nav.badges.drafts"),
    "/runs": t("nav.badges.failedRuns"),
    "/integrations/mcp": t("nav.badges.disabledMcp"),
  };

  useEffect(() => {
    const active = navGroups.find((group) =>
      group.items.some((item) => isActive(location.pathname, item.to)),
    );
    const title = active?.title;
    if (!title) {
      return;
    }
    setOpenGroups((prev) => {
      if (prev[title]) {
        return prev;
      }
      const next = { ...prev, [title]: true };
      window.localStorage.setItem(NAV_OPEN_KEY, JSON.stringify(next));
      return next;
    });
  }, [location.pathname, navGroups]);

  const toggleGroup = (title: string) => {
    setOpenGroups((prev) => {
      const next = { ...prev, [title]: !prev[title] };
      window.localStorage.setItem(NAV_OPEN_KEY, JSON.stringify(next));
      return next;
    });
  };

  return (
    <AppShell header={{ height: 56 }} navbar={{ width: 248, breakpoint: "sm" }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" wrap="nowrap">
          <Title order={4}>
            <Link to="/agents" style={{ color: "inherit", textDecoration: "none" }}>
              ai-agents
            </Link>
          </Title>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs">
        <AppShell.Section grow component={ScrollArea}>
          {navGroups.map((group, index) => (
            <Box key={group.title ?? `group-${index}`} mb={index === navGroups.length - 1 ? 0 : 6}>
              {group.title ? (
                <UnstyledButton
                  w="100%"
                  px="sm"
                  pt="sm"
                  pb={4}
                  onClick={() => toggleGroup(group.title!)}
                  aria-expanded={Boolean(openGroups[group.title!])}
                  aria-label={group.title}
                >
                  <Group justify="space-between" wrap="nowrap">
                    <Text size="xs" c="dimmed" fw={600} tt="uppercase">
                      {group.title}
                    </Text>
                    <Box
                      style={{
                        transform: openGroups[group.title!]
                          ? "rotate(0deg)"
                          : "rotate(-90deg)",
                        transition: "transform 120ms ease",
                        display: "flex",
                      }}
                    >
                      <ChevronDownIcon />
                    </Box>
                  </Group>
                </UnstyledButton>
              ) : null}
              <Collapse expanded={group.title ? Boolean(openGroups[group.title!]) : true}>
                <NavItemList
                  items={group.items}
                  pathname={location.pathname}
                  counts={navCounts}
                  titles={navBadgeTitles}
                />
              </Collapse>
              {index < navGroups.length - 1 ? <Divider my="xs" /> : null}
            </Box>
          ))}
        </AppShell.Section>

        <Divider my="xs" />
        <AppShell.Section>
          <Menu position="top-start" width="target" withArrow shadow="md">
            <Menu.Target>
              <UnstyledButton w="100%" px="xs" py={8} style={{ borderRadius: 8 }} className="user-menu">
                <Group gap={10} wrap="nowrap">
                  <Avatar name={userLabel} color="initials" radius="xl" size="md" />
                  <Box style={{ minWidth: 0, flex: 1 }}>
                    <Text size="sm" fw={500} truncate title={userLabel}>
                      {userLabel}
                    </Text>
                    <Badge size="xs" variant="light" color={ROLE_COLOR[role]} mt={2}>
                      {t(`roles.${role}`)}
                    </Badge>
                  </Box>
                </Group>
              </UnstyledButton>
            </Menu.Target>

            <Menu.Dropdown>
              <Menu.Label>
                {userLabel}
                {me.user.email ? ` · ${me.user.email}` : ""}
              </Menu.Label>
              <Menu.Label>{t("userMenu.theme")}</Menu.Label>
              <Box px="sm" pb="xs">
                <ThemeSwitcher size="xs" />
              </Box>
              <Menu.Label>{t("userMenu.language")}</Menu.Label>
              <Box px="sm" pb="xs">
                <LanguageSwitcher size="xs" />
              </Box>

              <Menu.Divider />
              <Menu.Item component={Link} to="/settings">
                {t("userMenu.settings")}
              </Menu.Item>
              <Menu.Item component={Link} to="/docs">
                {t("userMenu.docs")}
              </Menu.Item>
              <Menu.Item component={Link} to="/about">
                {t("userMenu.about")}
              </Menu.Item>

              <Menu.Divider />
              <Menu.Item color="red" disabled={busy} onClick={() => void handleLogout()}>
                {t("userMenu.logout")}
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main>
        <AssistProvider>
          <CommandPalette
            opened={paletteOpen}
            onClose={() => setPaletteOpen(false)}
            nav={navGroups.flatMap((group) => group.items)}
          />
          <Outlet context={{ me } satisfies LayoutOutlet} />
          <AssistPanel />
        </AssistProvider>
      </AppShell.Main>
    </AppShell>
  );
}

function NavItemList({
  items,
  pathname,
  counts,
  titles,
}: {
  items: NavItem[];
  pathname: string;
  counts: Record<string, number>;
  titles: Record<string, string>;
}): ReactNode {
  return (
    <>
      {items.map((item) => {
        const count = counts[item.to] ?? 0;
        return (
          <NavLink
            key={item.to}
            component={Link}
            to={item.to}
            label={item.label}
            leftSection={NAV_ICONS[item.to]}
            active={isActive(pathname, item.to)}
            variant="filled"
            rightSection={
              count > 0 ? (
                <Badge
                  size="xs"
                  variant="light"
                  color={item.to === "/runs" ? "red" : "gray"}
                  title={`${count} ${titles[item.to] ?? ""}`.trim()}
                >
                  {count}
                </Badge>
              ) : undefined
            }
          />
        );
      })}
    </>
  );
}
