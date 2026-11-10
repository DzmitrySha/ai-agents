"""Plugin registry for `kind=plugin` agents.

Plugins are code-registered (no dynamic loading): deploy a backend build that
registers the plugin under the name stored in `agents.plugin_name`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

from app.agents.events import AgentEvent
from app.runtime.models import LLMConfig

StreamFn = Callable[[str, LLMConfig | None, int], AsyncIterator[AgentEvent]]

PLUGINS: dict[str, StreamFn] = {}


def register_plugin(name: str, stream: StreamFn) -> None:
    PLUGINS[name] = stream


def get_plugin(name: str) -> StreamFn:
    try:
        return PLUGINS[name]
    except KeyError as exc:
        raise RuntimeError(f"unknown plugin: {name}") from exc
