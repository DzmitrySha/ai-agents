/** MultiSelect with a shared «Select all» option for catalog allowlists. */

import { Checkbox, Group, MultiSelect, Stack, Text } from "@mantine/core";
import { useTranslation } from "react-i18next";

type Option = { value: string; label: string };

const ALL_OPTION = "__all__";

type Props = {
  label: string;
  description?: string;
  data: Option[];
  value: string[];
  onChange: (value: string[]) => void;
  disabled?: boolean;
  nothingFoundMessage?: string;
  size?: "xs" | "sm" | "md";
};

export function AllowlistMultiSelect({
  label,
  description,
  data,
  value,
  onChange,
  disabled = false,
  nothingFoundMessage,
  size,
}: Props) {
  const { t } = useTranslation();
  const allValues = data.map((item) => item.value);
  const allSelected = allValues.length > 0 && allValues.every((v) => value.includes(v));
  const options = allValues.length
    ? [
        {
          value: ALL_OPTION,
          label: allSelected ? t("common.clearAll") : t("common.selectAll"),
        },
        ...data,
      ]
    : data;
  const change = (next: string[]) => {
    if (next.includes(ALL_OPTION)) {
      onChange(allSelected ? [] : allValues);
      return;
    }
    onChange(next.filter((item) => item !== ALL_OPTION));
  };

  return (
    <Stack gap={4}>
      <Text size={size === "xs" ? "xs" : "sm"} fw={500}>
        {label}
      </Text>
      <MultiSelect
        description={description}
        data={options}
        value={value}
        onChange={change}
        disabled={disabled}
        searchable
        clearable
        size={size}
        nothingFoundMessage={nothingFoundMessage}
        withCheckIcon={false}
        filter={({ options: items, search }) => {
          const query = search.trim().toLowerCase();
          return items.filter((item) => {
            if ("value" in item && item.value === ALL_OPTION) {
              return true;
            }
            return (
              "label" in item &&
              (!query || String(item.label).toLowerCase().includes(query))
            );
          });
        }}
        renderOption={({ option }) => {
          const checked =
            option.value === ALL_OPTION
              ? allSelected
              : value.includes(option.value);
          return (
            <Group gap="sm" wrap="nowrap">
              <Checkbox
                checked={checked}
                readOnly
                tabIndex={-1}
                aria-hidden
                style={{ pointerEvents: "none" }}
              />
              <Text size="sm" fw={option.value === ALL_OPTION ? 600 : 400}>
                {option.label}
              </Text>
            </Group>
          );
        }}
      />
    </Stack>
  );
}
