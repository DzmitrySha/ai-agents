import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Modal,
  NumberInput,
  Select,
  Stack,
  Table,
  Text,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { apiFetch, jsonBody } from "../api";
import { formatDate } from "../format";
import { DirectoryPicker } from "../components/DirectoryPicker";
import { PageHeader, PageSearch } from "../components/PageHeader";
import { NO_AUTOFILL } from "../formAttrs";
import { useSession } from "../components/AppLayout";
import { useAssistForm } from "../assist";
import { matchesPageSearch } from "../pageSearch";
import type { AdminUser, AppRole, IdentityUser } from "../types";
import { useBaselineDirty, useUnsavedGuard } from "../unsavedChanges";

type NumberField = number | string;

const ROLE_COLORS: Record<AppRole, string> = {
  superadmin: "grape",
  admin: "blue",
  user: "green",
};

function UserRow({
  user,
  canManageSuperadmins,
  roleOptions,
  onSaved,
  onError,
}: {
  user: AdminUser;
  canManageSuperadmins: boolean;
  roleOptions: { value: AppRole; label: string }[];
  onSaved: (value: AdminUser) => void;
  onError: (message: string) => void;
}) {
  const { t } = useTranslation();
  const [role, setRole] = useState<AppRole>(user.app_role);
  const [limit, setLimit] = useState<number | string>(user.daily_run_limit ?? "");
  const [saving, setSaving] = useState(false);
  const normalizedLimit = typeof limit === "number" ? limit : null;
  const limitDirty = normalizedLimit !== (user.daily_run_limit ?? null);

  const patch = async (payload: Record<string, unknown>) => {
    setSaving(true);
    try {
      const updated = await apiFetch<AdminUser>(
        `/api/admin/users/${encodeURIComponent(user.id)}`,
        { method: "PATCH", body: jsonBody(payload) },
      );
      onSaved(updated);
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
      throw err;
    } finally {
      setSaving(false);
    }
  };

  useUnsavedGuard(`user-limit-${user.id}`, limitDirty, async () => {
    await patch({ daily_run_limit: normalizedLimit });
  });

  return (
    <Table.Tr>
      <Table.Td>
        <Text size="sm">{user.display_name || user.email || user.id}</Text>
        <Text size="xs" c="dimmed" ff="monospace">
          {user.id}
        </Text>
      </Table.Td>
      <Table.Td>
        <Group gap={4}>
          <Badge color={ROLE_COLORS[user.app_role]} variant="light">
            {user.app_role}
          </Badge>
          {user.is_bootstrap ? (
            <Badge color="gray" variant="outline">
              bootstrap
            </Badge>
          ) : null}
        </Group>
      </Table.Td>
      <Table.Td>
        <Select
          size="xs"
          data={
            canManageSuperadmins
              ? roleOptions
              : roleOptions.filter((option) => option.value !== "superadmin")
          }
          value={role}
          allowDeselect={false}
          disabled={
            saving ||
            user.is_bootstrap ||
            (user.is_superadmin && !canManageSuperadmins)
          }
          onChange={(value) => {
            const next = (value as AppRole | null) ?? "user";
            setRole(next);
            void patch({ app_role: next });
          }}
        />
      </Table.Td>
      <Table.Td>
        <NumberInput {...NO_AUTOFILL}
          size="xs"
          min={0}
          max={100000}
          placeholder={t("users.dailyLimitPlaceholder")}
          value={limit}
          disabled={saving}
          onChange={setLimit}
          onBlur={() => {
            const next = typeof limit === "number" ? limit : null;
            if (next !== user.daily_run_limit) {
              void patch({ daily_run_limit: next });
            }
          }}
          w={110}
        />
      </Table.Td>
      <Table.Td>{user.runs_today}</Table.Td>
      <Table.Td>
        <Text size="xs" c="dimmed">
          {user.last_login_at ? formatDate(user.last_login_at) : t("common.emptyDash")}
        </Text>
      </Table.Td>
    </Table.Tr>
  );
}

export function UsersPage() {
  const { t } = useTranslation();
  const me = useSession();
  const canManageSuperadmins = Boolean(me.user.can_manage_superadmins);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [selectedIdentity, setSelectedIdentity] = useState<IdentityUser | null>(null);
  const [busy, setBusy] = useState(false);
  const emptyUserDraft = {
    sub: "",
    email: "",
    display_name: "",
    app_role: "user" as AppRole,
    daily_run_limit: "" as NumberField,
  };
  const [draft, setDraft] = useState(emptyUserDraft);
  const addSnapshot = {
    draft,
    identitySub: selectedIdentity?.sub ?? "",
  };
  const { dirty: addDirty, captureBaseline: captureAdd } = useBaselineDirty(addSnapshot, addOpen);
  const [pageSearch, setPageSearch] = useState("");

  const visibleUsers = useMemo(() => {
    if (!pageSearch.trim()) {
      return users;
    }
    return users.filter((user) =>
      matchesPageSearch(pageSearch, [
        user.id,
        user.email,
        user.display_name,
        user.app_role,
        user.is_superadmin ? "superadmin" : "",
        user.is_bootstrap ? "bootstrap" : "",
      ]),
    );
  }, [users, pageSearch]);

  const roleOptions = useMemo(
    () =>
      (["superadmin", "admin", "user"] as const).map((value) => ({
        value: value as AppRole,
        label: t(`users.roleOptions.${value}`),
      })),
    [t],
  );

  useAssistForm(
    "user",
    addOpen
      ? {
          page_search: pageSearch,
          app_role: draft.app_role,
          daily_run_limit: draft.daily_run_limit,
          can_manage_superadmins: canManageSuperadmins,
        }
      : {
          page_search: pageSearch,
          can_manage_superadmins: canManageSuperadmins,
          users: users.map((user) => ({
            id: user.id,
            email: user.email,
            display_name: user.display_name,
            app_role: user.app_role,
          })),
        },
    (fields) => {
      const { page_search: _ps, ...rest } = fields;
      const next = { ...draft };
      let touched = false;
      const role = String(rest.app_role ?? "");
      if (["admin", "user", "superadmin"].includes(role)) {
        if (role === "superadmin" && !canManageSuperadmins) {
          return t("users.superadminOnlyBootstrap");
        }
        next.app_role = role as AppRole;
        touched = true;
      }
      const limit = Number(rest.daily_run_limit);
      if (Number.isFinite(limit) && limit >= 0) {
        next.daily_run_limit = Math.round(limit);
        touched = true;
      }
      if (!touched) {
        return Object.keys(rest).length === 0 ? null : t("users.noUserFields");
      }
      if (!addOpen) {
        captureAdd({ draft: emptyUserDraft, identitySub: "" });
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

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setUsers(await apiFetch<AdminUser[]>("/api/admin/users"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const replace = (value: AdminUser) => {
    setUsers((prev) => prev.map((item) => (item.id === value.id ? value : item)));
    setNotice(t("users.updated", { id: value.id }));
  };

  const persistCreate = async () => {
    const created = await apiFetch<AdminUser>("/api/admin/users", {
      method: "POST",
      body: jsonBody({
        sub: draft.sub.trim(),
        email: draft.email.trim() || null,
        display_name: draft.display_name.trim() || null,
        app_role: draft.app_role,
        daily_run_limit:
          typeof draft.daily_run_limit === "number" ? draft.daily_run_limit : null,
      }),
    });
    setUsers((prev) => [created, ...prev]);
    captureAdd({ draft: emptyUserDraft, identitySub: "" });
    setAddOpen(false);
    setSelectedIdentity(null);
    setDraft(emptyUserDraft);
    setNotice(t("users.created", { id: created.id }));
  };

  const handleCreate = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await persistCreate();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const openAdd = () => {
    setSelectedIdentity(null);
    setDraft(emptyUserDraft);
    captureAdd({ draft: emptyUserDraft, identitySub: "" });
    setAddOpen(true);
  };

  const closeAdd = () => setAddOpen(false);

  const { requestLeave: requestAddLeave } = useUnsavedGuard(
    "user-create-modal",
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

  return (
    <Stack gap="md">
      <PageHeader title={t("users.title")}>
        <PageSearch value={pageSearch} onChange={setPageSearch} />
        <Button onClick={openAdd}>{t("users.add")}</Button>
      </PageHeader>

      {error ? (
        <Alert color="red" title={t("common.error")}>
          {error}
        </Alert>
      ) : null}
      {notice ? <Alert color="green">{notice}</Alert> : null}

      <Card withBorder>
        <Stack gap="sm">
          <Text size="sm" c="dimmed">
            {t("users.intro")}
          </Text>
          {loading ? (
            <Group justify="center" py="md">
              <Loader size="sm" />
            </Group>
          ) : visibleUsers.length === 0 && users.length > 0 ? (
            <Text size="sm" c="dimmed">
              {t("common.emptyPageFilter")}
            </Text>
          ) : (
            <Table.ScrollContainer minWidth={900}>
              <Table striped highlightOnHover verticalSpacing="xs">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t("users.columns.user")}</Table.Th>
                    <Table.Th>{t("users.columns.role")}</Table.Th>
                    <Table.Th>{t("users.columns.changeRole")}</Table.Th>
                    <Table.Th>{t("users.columns.dailyLimit")}</Table.Th>
                    <Table.Th>{t("users.columns.runsToday")}</Table.Th>
                    <Table.Th>{t("users.columns.login")}</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {visibleUsers.map((user) => (
                    <UserRow
                      key={user.id}
                      user={user}
                      canManageSuperadmins={canManageSuperadmins}
                      roleOptions={roleOptions}
                      onSaved={replace}
                      onError={setError}
                    />
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
        </Stack>
      </Card>

      <Modal
        opened={addOpen}
        onClose={() => requestAddLeave(closeAdd)}
        title={t("users.addTitle")}
      >
        <Stack gap="sm">
          <DirectoryPicker
            value={selectedIdentity}
            onChange={(user) => {
              setSelectedIdentity(user);
              setDraft((prev) => ({
                ...prev,
                sub: user?.sub ?? "",
                email: user?.email ?? "",
                display_name: user?.display_name ?? "",
              }));
            }}
          />
          <Select
            {...NO_AUTOFILL}
            label={t("users.roleSelect")}
            description={
              canManageSuperadmins ? undefined : t("users.roleSuperadminHint")
            }
            data={
              canManageSuperadmins
                ? roleOptions
                : roleOptions.filter((option) => option.value !== "superadmin")
            }
            value={draft.app_role}
            allowDeselect={false}
            onChange={(value) =>
              setDraft((prev) => ({
                ...prev,
                app_role: (value as AppRole | null) ?? "user",
              }))
            }
          />
          <NumberInput
            {...NO_AUTOFILL}
            label={t("users.dailyLimit")}
            description={t("users.dailyLimitHint")}
            min={0}
            max={100000}
            value={draft.daily_run_limit}
            onChange={(value) =>
              setDraft((prev) => ({ ...prev, daily_run_limit: value }))
            }
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={() => requestAddLeave(closeAdd)}>
              {t("common.cancel")}
            </Button>
            <Button onClick={() => void handleCreate()} loading={busy} disabled={!draft.sub.trim()}>
              {t("common.add")}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
