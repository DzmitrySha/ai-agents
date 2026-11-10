"""Tool registry exposed to preset agents and `/v1/tools`."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.tools import BaseTool, tool

_ALLOWED_EXPRESSION_CHARS = set("0123456789+-*/().% ")

_TZ_ALIASES = {
    "moscow": "Europe/Moscow",
    "minsk": "Europe/Minsk",
    "belarus": "Europe/Minsk",
    "utc+3": "Europe/Moscow",
    "utc+3:00": "Europe/Moscow",
    "gmt+3": "Europe/Moscow",
}


@tool
def get_server_time() -> str:
    """Return the current server time in UTC (ISO-8601)."""
    return datetime.now(timezone.utc).isoformat()


@tool
def calculator(expression: str) -> str:
    """Evaluate a basic arithmetic expression (+ - * / % parentheses and numbers)."""
    if not expression or any(char not in _ALLOWED_EXPRESSION_CHARS for char in expression):
        return f"error: недопустимое выражение '{expression}'"
    try:
        value = eval(expression, {"__builtins__": {}}, {})  # noqa: S307 - char allowlist above
    except Exception as exc:  # noqa: BLE001 - report to the agent as text
        return f"error: {type(exc).__name__}: {exc}"
    return str(value)


@tool
def now(timezone_name: str = "Europe/Moscow") -> str:
    """Return the current time in the given IANA timezone (Moscow by default)."""
    raw = (timezone_name or "Europe/Moscow").strip()
    key = raw.lower()
    zone_name = _TZ_ALIASES.get(key, raw)
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return f"error: неизвестная таймзона '{timezone_name}'"
    return datetime.now(zone).isoformat()


TOOLS: dict[str, BaseTool] = {
    "get_server_time": get_server_time,
    "calculator": calculator,
    "now": now,
}


def tool_specs() -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for name, tool_obj in TOOLS.items():
        specs.append(
            {
                "name": name,
                "description": tool_obj.description or "",
                "parameters": tool_obj.args_schema.model_json_schema(),  # type: ignore[union-attr]
            }
        )
    return specs


TOOL_SPECS = tool_specs()
