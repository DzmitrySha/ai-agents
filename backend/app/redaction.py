"""Best-effort secret redaction for logs and run error messages."""

from __future__ import annotations

import re

# Order matters: specific token shapes first, then key/value pairs and DSNs.
SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE), "Bearer ***"),
    (re.compile(r"sk-[A-Za-z0-9*._-]{8,}"), "sk-***"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "ghp_***"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "xox-***"),
    (
        re.compile(r"postgres(?:ql)?://[^:\s]+:[^@\s]+@", re.IGNORECASE),
        "postgres://***:***@",
    ),
    (
        re.compile(
            r"(?i)\b(authorization|api[_-]?key|token|secret|password)\s*[:=]\s*"
            r"(?!Bearer\b)[^\s,;\"']+"
        ),
        "***",
    ),
)


def redact_text(value: str) -> str:
    """Replace common credential shapes with stable placeholders."""
    text = value if isinstance(value, str) else str(value)
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text
