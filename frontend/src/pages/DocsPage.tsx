import { type ReactNode, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Anchor,
  Card,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { useAssistForm } from "../assist";
import { Markdown } from "../components/Markdown";
import { PageHeader, PageSearch } from "../components/PageHeader";
import { matchesPageSearch } from "../pageSearch";

type DocCardId = "agentsSkillsTools" | "externalApi" | "apiContract";

const DOC_ROUTES: { id: DocCardId; path: string }[] = [
  { id: "agentsSkillsTools", path: "agents-skills-tools" },
  { id: "externalApi", path: "external-api" },
  { id: "apiContract", path: "api" },
];

function cardIdFromPath(slug: string | undefined): DocCardId | null {
  const hit = DOC_ROUTES.find((item) => item.path === slug);
  return hit?.id ?? null;
}

export function DocsPage() {
  const { t } = useTranslation();
  const { slug } = useParams<{ slug?: string }>();
  const active = cardIdFromPath(slug);
  const [pageSearch, setPageSearch] = useState("");

  const filteredDocRoutes = useMemo(() => {
    if (!pageSearch.trim()) {
      return DOC_ROUTES;
    }
    return DOC_ROUTES.filter((item) =>
      matchesPageSearch(pageSearch, [
        t(`docs.cards.${item.id}.title`),
        t(`docs.cards.${item.id}.summary`),
      ]),
    );
  }, [pageSearch, t]);

  useAssistForm(
    "general",
    {
      page_search: pageSearch,
      docs: DOC_ROUTES.map((item) => ({
        id: item.id,
        path: item.path,
        title: t(`docs.cards.${item.id}.title`),
      })),
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

  if (active) {
    const title = t(`docs.cards.${active}.title`);
    const bodyMd = t(`docs.cards.${active}.bodyMd`);
    return (
      <Stack gap="md">
        <GroupWithSearch
          title={title}
          pageSearch={pageSearch}
          onPageSearch={setPageSearch}
          back={
            <Anchor component={Link} to="/docs" size="sm">
              {t("common.back")}
            </Anchor>
          }
        />
        <Markdown>{bodyMd}</Markdown>
      </Stack>
    );
  }

  return (
    <Stack gap="md">
      <GroupWithSearch
        title={t("docs.title")}
        pageSearch={pageSearch}
        onPageSearch={setPageSearch}
      />
      <Text c="dimmed">{t("docs.subtitle")}</Text>
      {filteredDocRoutes.length === 0 ? (
        <Text size="sm" c="dimmed">
          {t("common.emptyPageFilter")}
        </Text>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
          {filteredDocRoutes.map((item) => (
            <Card
              key={item.id}
              component={Link}
              to={`/docs/${item.path}`}
              withBorder
              padding="lg"
              radius="md"
              style={{ textDecoration: "none", color: "inherit" }}
            >
              <Title order={4}>{t(`docs.cards.${item.id}.title`)}</Title>
              <Text size="sm" c="dimmed" mt="xs">
                {t(`docs.cards.${item.id}.summary`)}
              </Text>
            </Card>
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}

function GroupWithSearch({
  title,
  pageSearch,
  onPageSearch,
  back,
}: {
  title: string;
  pageSearch: string;
  onPageSearch: (value: string) => void;
  back?: ReactNode;
}) {
  return (
    <PageHeader title={title}>
      <PageSearch value={pageSearch} onChange={onPageSearch} />
      {back}
    </PageHeader>
  );
}
