import { SegmentedControl, type MantineSize } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { setAppLocale, type AppLocale } from "../i18n";

export function LanguageSwitcher({ size = "xs" }: { size?: MantineSize }) {
  const { t, i18n } = useTranslation();
  const value: AppLocale = i18n.language?.startsWith("en") ? "en" : "ru";

  return (
    <SegmentedControl
      size={size}
      value={value}
      onChange={(next) => void setAppLocale(next as AppLocale)}
      data={[
        { label: t("language.ru"), value: "ru" },
        { label: t("language.en"), value: "en" },
      ]}
      aria-label={t("language.label")}
    />
  );
}
