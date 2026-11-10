/** Поиск по странице списка: подстрока без учёта регистра по нескольким полям. */

export function normalizePageSearch(value: string): string {
  return value.trim().toLowerCase();
}

export function matchesPageSearch(
  needle: string,
  haystacks: (string | number | boolean | null | undefined)[],
): boolean {
  const n = normalizePageSearch(needle);
  if (!n) {
    return true;
  }
  return haystacks.some((item) => {
    if (item === null || item === undefined) {
      return false;
    }
    return String(item).toLowerCase().includes(n);
  });
}
