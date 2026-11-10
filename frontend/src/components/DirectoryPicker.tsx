import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Combobox,
  Input,
  InputBase,
  Loader,
  Text,
  useCombobox,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { apiFetch } from "../api";
import { NO_AUTOFILL } from "../formAttrs";
import type { IdentityUser, IdentityUserPage } from "../types";

const PAGE_SIZE = 20;
const SCROLL_THRESHOLD = 48;

interface Props {
  value: IdentityUser | null;
  onChange: (user: IdentityUser | null) => void;
}

/**
 * Пользователь выбирается из каталога Keycloak: поиск на сервере,
 * догрузка следующей страницы при прокрутке списка.
 */
export function DirectoryPicker({ value, onChange }: Props) {
  const { t } = useTranslation();
  const combobox = useCombobox({
    onDropdownClose: () => combobox.resetSelectedOption(),
  });
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<IdentityUser[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);
  const loadingRef = useRef(false);
  const listRef = useRef<HTMLDivElement>(null);

  const load = async (reset: boolean, search: string) => {
    if (!reset && loadingRef.current) {
      return;
    }
    loadingRef.current = true;
    const keepScroll = reset ? 0 : (listRef.current?.scrollTop ?? 0);
    const current = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const first = reset ? 0 : items.length;
      const page = await apiFetch<IdentityUserPage>(
        `/api/admin/identity-users?q=${encodeURIComponent(search.trim())}&limit=${PAGE_SIZE}&first=${first}`,
      );
      if (current !== requestId.current) {
        return;
      }
      setItems((prev) => (reset ? page.items : [...prev, ...page.items]));
      setHasMore(page.has_more);
    } catch (err) {
      if (current === requestId.current) {
        setError(err instanceof Error ? err.message : String(err));
        setItems([]);
        setHasMore(false);
      }
    } finally {
      if (current === requestId.current) {
        setLoading(false);
        // Возвращаем позицию: после append список не должен прыгать наверх.
        window.requestAnimationFrame(() => {
          if (listRef.current) {
            listRef.current.scrollTop = keepScroll;
          }
        });
      }
      loadingRef.current = false;
    }
  };

  // Debounce: новый запрос после паузы, при открытии и смене строки поиска.
  useEffect(() => {
    if (combobox.dropdownOpened === false) {
      return;
    }
    const timer = window.setTimeout(() => {
      void load(true, query);
    }, 300);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, combobox.dropdownOpened]);

  const handleScroll = (event: React.UIEvent<HTMLDivElement>) => {
    const node = event.currentTarget;
    const remaining = node.scrollHeight - node.scrollTop - node.clientHeight;
    if (remaining < SCROLL_THRESHOLD && hasMore && !loading) {
      void load(false, query);
    }
  };

  const selectedLabel = value
    ? `${value.display_name ?? value.username}${value.email ? ` <${value.email}>` : ""}`
    : "";

  const emptyMessage = loading
    ? t("ai-agentsId.loading")
    : items.length === 0
      ? t("ai-agentsId.noneFound")
      : hasMore
        ? t("ai-agentsId.scrollMore")
        : t("ai-agentsId.endOfList");

  return (
    <Box>
      <Combobox
        store={combobox}
        onOptionSubmit={(sub) => {
          const found = items.find((item) => item.sub === sub) ?? null;
          onChange(found);
          combobox.closeDropdown();
        }}
      >
        <Combobox.Target>
          <InputBase
            component="button"
            type="button"
            label={t("ai-agentsId.label")}
            description={t("ai-agentsId.description")}
            rightSection={loading ? <Loader size={14} /> : <Combobox.Chevron />}
            rightSectionPointerEvents="none"
            onClick={() => combobox.toggleDropdown()}
            {...NO_AUTOFILL}
          >
            {value ? selectedLabel : <Input.Placeholder>{t("ai-agentsId.placeholder")}</Input.Placeholder>}
          </InputBase>
        </Combobox.Target>

        <Combobox.Dropdown>
          <Combobox.Search
            value={query}
            onChange={(event) => setQuery(event.currentTarget.value)}
            placeholder={t("ai-agentsId.searchPlaceholder")}
            {...NO_AUTOFILL}
          />
          <Combobox.Options
            ref={listRef}
            mah={280}
            style={{ overflowY: "auto" }}
            onScroll={handleScroll}
          >
            {items.map((item) => (
              <Combobox.Option value={item.sub} key={item.sub}>
                <Text size="sm">
                  {item.display_name ?? item.username}
                  {item.email ? (
                    <Text span size="xs" c="dimmed">
                      {" "}
                      &lt;{item.email}&gt;
                    </Text>
                  ) : null}
                </Text>
                {item.enabled ? null : (
                  <Text size="xs" c="orange">
                    {t("ai-agentsId.disabledInDirectory")}
                  </Text>
                )}
              </Combobox.Option>
            ))}
            <Combobox.Empty>
              <Text size="xs" c="dimmed">
                {emptyMessage}
              </Text>
            </Combobox.Empty>
          </Combobox.Options>
        </Combobox.Dropdown>
      </Combobox>

      {value ? (
        <Text size="xs" c="dimmed" mt={4}>
          {t("ai-agentsId.selected", { sub: value.sub })}
          {value.email ? ` · ${value.email}` : ""}
        </Text>
      ) : null}
      {error ? (
        <Alert color="orange" title={t("ai-agentsId.catalogUnavailable")} mt="xs">
          {error}
        </Alert>
      ) : null}
    </Box>
  );
}
