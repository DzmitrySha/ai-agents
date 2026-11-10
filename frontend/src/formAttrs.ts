/**
 * Гасит автозаполнение и навязчивые оверлеи расширений (1Password, LastPass,
 * Bitwarden, Dashlane) на полях приложения: это не логин-формы, подсказки мешают.
 */
export const NO_AUTOFILL = {
  autoComplete: "off",
  spellCheck: false,
  "data-1p-ignore": "true",
  "data-lpignore": "true",
  "data-bwignore": "true",
  "data-dashlane-ignore": "true",
  "data-form-type": "other",
};

/**
 * Description под input: в SimpleGrid соседние поля (Название / Slug) остаются
 * на одной линии по label и по самому полю ввода.
 */
export const FIELD_ORDER = ["label", "input", "description", "error"] as const;
