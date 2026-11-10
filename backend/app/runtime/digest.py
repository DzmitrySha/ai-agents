"""Compact trajectory digest built from persisted run events (on demand)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.models import RunEventRow, RunRow


def _duration_ms(run: RunRow) -> int | None:
    if run.started_at is None or run.finished_at is None:
        return None
    delta = run.finished_at - run.started_at
    return max(0, int(delta.total_seconds() * 1000))


def build_digest(
    run: RunRow, events: Sequence[RunEventRow]
) -> dict[str, Any]:
    steps = 0
    pending: list[str] = []
    calls: dict[str, int] = {}
    errors: dict[str, int] = {}
    total_tool_calls = 0

    for event in events:
        data = event.data or {}
        if event.event == "agent.step":
            steps += 1
        elif event.event == "tool.call":
            tool = str(data.get("tool") or "unknown")
            pending.append(tool)
            calls[tool] = calls.get(tool, 0) + 1
            total_tool_calls += 1
        elif event.event == "tool.result":
            tool = str(data.get("tool") or "unknown")
            if tool in pending:
                pending.remove(tool)
            elif pending:
                pending.pop(0)
            if str(data.get("output") or "").startswith("error:"):
                errors[tool] = errors.get(tool, 0) + 1

    tool_calls = [
        {"tool": tool, "calls": calls[tool], "errors": errors.get(tool, 0)}
        for tool in sorted(calls)
    ]

    return {
        "run_id": run.id,
        "agent_id": run.agent_slug,
        "agent_version": None,
        "harness_hash": run.harness_hash,
        "status": run.status,
        "duration_ms": _duration_ms(run),
        "steps": steps,
        "events_total": len(events),
        "tool_calls": tool_calls,
        "total_tool_calls": total_tool_calls,
        "failed_tool_calls": sum(errors.values()),
        "unfinished_tool_calls": len(pending),
        "output_chars": len(run.output or ""),
        "error": run.error,
        "prompt_tokens": run.prompt_tokens,
        "completion_tokens": run.completion_tokens,
        "total_tokens": run.total_tokens,
        "failure_kind": run.failure_kind,
        "attempts": run.attempts,
    }
