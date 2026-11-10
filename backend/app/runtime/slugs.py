"""Slug helpers shared by agents, tools and skills."""

from __future__ import annotations

import re

from app.runtime.models import SLUG_RE

_CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slugify(value: str) -> str:
    """Latin slug from arbitrary text (Cyrillic transliterated); '' when unusable."""
    lowered = (value or "").strip().lower()
    latin = "".join(_CYRILLIC.get(char, char) for char in lowered)
    slug = re.sub(r"[^a-z0-9]+", "-", latin).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)[:63].rstrip("-")
    return slug if SLUG_RE.match(slug) else ""


def unique_slug(value: str, used: set[str]) -> str:
    slug = value
    counter = 2
    while slug in used:
        slug = f"{value[:60]}-{counter}"
        counter += 1
    return slug
