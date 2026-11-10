"""Agent stream event type."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentEvent:
    type: str  # message.delta | tool.call | tool.result | agent.step
    data: dict[str, Any] = field(default_factory=dict)
