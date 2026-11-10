import { SegmentedControl, type MantineSize } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { useThemeMode, type ThemeMode } from "../theme";

export function ThemeSwitcher({ size = "xs" }: { size?: MantineSize }) {
  const { t } = useTranslation();
  const { mode, setMode } = useThemeMode();
  return (
    <SegmentedControl
      size={size}
      value={mode}
      onChange={(value) => setMode(value as ThemeMode)}
      data={[
        { label: t("theme.light"), value: "light" },
        { label: t("theme.dark"), value: "dark" },
        { label: t("theme.portracker"), value: "portracker" },
      ]}
      aria-label={t("theme.ariaLabel")}
    />
  );
}
