import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Anchor,
  List,
  Paper,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { useAssistForm } from "../assist";
import { PageHeader, PageSearch } from "../components/PageHeader";
import { matchesPageSearch } from "../pageSearch";

const APP_VERSION = "0.1.0";

export function AboutPage() {
  const { t } = useTranslation();
  const [pageSearch, setPageSearch] = useState("");
  const blurbs = t("about.blurb", { returnObjects: true }) as string[];
  const stack = t("about.stack", { returnObjects: true }) as string[];

  const linkDefs = useMemo(
    () => [
      { to: "/docs", label: t("about.links.docs") },
      { to: "/docs/agents-skills-tools", label: t("about.links.agentsGuide") },
      { to: "/docs/external-api", label: t("about.links.externalApi") },
      { to: "/docs/api", label: t("about.links.api") },
    ],
    [t],
  );

  const filteredBlurbs = useMemo(() => {
    const list = Array.isArray(blurbs) ? blurbs : [];
    if (!pageSearch.trim()) {
      return list;
    }
    return list.filter((paragraph) => matchesPageSearch(pageSearch, [paragraph]));
  }, [blurbs, pageSearch]);

  const filteredStack = useMemo(() => {
    const list = Array.isArray(stack) ? stack : [];
    if (!pageSearch.trim()) {
      return list;
    }
    return list.filter((item) => matchesPageSearch(pageSearch, [item]));
  }, [stack, pageSearch]);

  const filteredLinks = useMemo(() => {
    if (!pageSearch.trim()) {
      return linkDefs;
    }
    return linkDefs.filter((item) => matchesPageSearch(pageSearch, [item.label, item.to]));
  }, [linkDefs, pageSearch]);

  useAssistForm(
    "general",
    {
      page_search: pageSearch,
      about: { version: APP_VERSION, section: "about" },
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
    <Stack gap="md">
      <PageHeader title={t("about.title")}>
        <PageSearch value={pageSearch} onChange={setPageSearch} />
      </PageHeader>
      <Text c="dimmed">{t("about.subtitle")}</Text>
      <Text size="sm">{t("about.version", { version: APP_VERSION })}</Text>

      <Paper withBorder p="md" radius="md">
        <Stack gap="sm">
          {filteredBlurbs.length === 0 && (Array.isArray(blurbs) ? blurbs : []).length > 0 ? (
            <Text size="sm" c="dimmed">
              {t("common.emptyPageFilter")}
            </Text>
          ) : (
            filteredBlurbs.map((paragraph) => (
              <Text key={paragraph.slice(0, 24)} size="sm">
                {paragraph}
              </Text>
            ))
          )}
        </Stack>
      </Paper>

      <div>
        <Title order={4} mb="xs">
          {t("about.stackTitle")}
        </Title>
        {filteredStack.length === 0 && (Array.isArray(stack) ? stack : []).length > 0 ? (
          <Text size="sm" c="dimmed">
            {t("common.emptyPageFilter")}
          </Text>
        ) : (
          <List size="sm" spacing={4}>
            {filteredStack.map((item) => (
              <List.Item key={item}>{item}</List.Item>
            ))}
          </List>
        )}
      </div>

      <div>
        <Title order={4} mb="xs">
          {t("about.linksTitle")}
        </Title>
        {filteredLinks.length === 0 ? (
          <Text size="sm" c="dimmed">
            {linkDefs.length === 0 ? "" : t("common.emptyPageFilter")}
          </Text>
        ) : (
          <Stack gap={6}>
            {filteredLinks.map((item) => (
              <Anchor key={item.to} component={Link} to={item.to}>
                {item.label}
              </Anchor>
            ))}
          </Stack>
        )}
      </div>
    </Stack>
  );
}
