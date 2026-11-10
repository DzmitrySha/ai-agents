import { useMemo, useState } from "react";
import { Box, Paper, Stack, Text, Title } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { useAssistForm } from "../assist";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { PageHeader, PageSearch } from "../components/PageHeader";
import { ThemeSwitcher } from "../components/ThemeSwitcher";
import { matchesPageSearch } from "../pageSearch";

export function PreferencesPage() {
  const { t } = useTranslation();
  const [pageSearch, setPageSearch] = useState("");

  const sections = useMemo(
    () => [
      {
        key: "language",
        title: t("settingsPrefs.languageSection"),
        description: t("settingsPrefs.languageDescription"),
        haystack: [t("settingsPrefs.languageSection"), t("settingsPrefs.languageDescription")],
        content: (
          <Box w="fit-content">
            <LanguageSwitcher size="xs" />
          </Box>
        ),
      },
      {
        key: "theme",
        title: t("settingsPrefs.themeSection"),
        description: t("settingsPrefs.themeDescription"),
        haystack: [t("settingsPrefs.themeSection"), t("settingsPrefs.themeDescription")],
        content: (
          <Box w="fit-content">
            <ThemeSwitcher size="xs" />
          </Box>
        ),
      },
    ],
    [t],
  );

  const visibleSections = useMemo(() => {
    if (!pageSearch.trim()) {
      return sections;
    }
    return sections.filter((section) => matchesPageSearch(pageSearch, section.haystack));
  }, [pageSearch, sections]);

  useAssistForm(
    "general",
    {
      page_search: pageSearch,
      sections: sections.map((s) => ({ key: s.key, title: s.title })),
    },
    (fields) => {
      const { page_search: _p, ...rest } = fields;
      if (Object.keys(rest).length === 0) {
        return null;
      }
      return t("assist.unexpectedFields");
    },
    (query) => {
      setPageSearch(query);
      return null;
    },
  );

  return (
    <Stack gap="md" maw={560}>
      <PageHeader title={t("settingsPrefs.title")}>
        <PageSearch value={pageSearch} onChange={setPageSearch} />
      </PageHeader>

      {visibleSections.length === 0 ? (
        <Text size="sm" c="dimmed">
          {t("common.emptyPageFilter")}
        </Text>
      ) : (
        visibleSections.map((section) => (
          <Paper key={section.key} withBorder p="md" radius="md">
            <Stack gap="xs">
              <div>
                <Title order={5}>{section.title}</Title>
                <Text size="xs" c="dimmed">
                  {section.description}
                </Text>
              </div>
              {section.content}
            </Stack>
          </Paper>
        ))
      )}
    </Stack>
  );
}
