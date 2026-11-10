import { useSearchParams } from "react-router-dom";
import { Alert, Button, Center, Paper, Stack, Text, Title } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { ThemeSwitcher } from "../components/ThemeSwitcher";

export function LoginPage() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const error = searchParams.get("error");

  return (
    <Center h="100vh" p="md">
      <Paper withBorder shadow="sm" p="xl" w={380}>
        <Stack gap="md">
          <div>
            <Title order={3}>{t("login.title")}</Title>
            <Text size="sm" c="dimmed">
              {t("login.subtitle")}
            </Text>
          </div>

          {error ? (
            <Alert color="red" title={t("login.loginFailed")}>
              {error}
            </Alert>
          ) : null}

          <Button component="a" href="/auth/login?return_to=/agents" fullWidth>
            {t("login.loginKeycloak")}
          </Button>

          <Text size="xs" c="dimmed">
            {t("login.cookieHint")}
          </Text>

          <ThemeSwitcher />
          <LanguageSwitcher />
        </Stack>
      </Paper>
    </Center>
  );
}
