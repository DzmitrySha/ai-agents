import type en from "./en";

/** Recursively widen string literal leaves so locales can differ in wording. */
type DeepStringify<T> = T extends string
  ? string
  : T extends readonly (infer U)[]
    ? DeepStringify<U>[]
    : T extends object
      ? { [K in keyof T]: DeepStringify<T[K]> }
      : T;

/**
 * Message tree inferred from the English catalog.
 * Use as `const ru: MessageTree = { ... }` so keys stay in sync with `en.ts`.
 */
export type MessageTree = DeepStringify<typeof en>;
