"""Per-run harness snapshot: effective config fingerprint without secrets."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.agents.execution import AgentConfig
from app.runtime.models import HarnessDiffItem, RunOut, TrajectoryDigest

HARNESS_VERSION = 5


def _sha256(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sanitize_tool(definition: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": definition.get("slug"),
        "name": definition.get("name"),
        "description": definition.get("description") or "",
        "method": definition.get("method"),
        "url": definition.get("url"),
        "header_names": sorted(str(name) for name in (definition.get("headers") or {})),
        "query_keys": sorted(str(name) for name in (definition.get("query") or {})),
        "body_template_sha256": _sha256(definition.get("body_template")),
        "content_type": definition.get("content_type"),
        "parameters": [dict(param) for param in definition.get("parameters") or []],
        "timeout_seconds": definition.get("timeout_seconds"),
    }


def _sanitize_mcp(definition: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref": definition.get("ref"),
        "connection": definition.get("connection"),
        "url": definition.get("url"),
        "tool": definition.get("tool"),
        "timeout_seconds": definition.get("timeout_seconds"),
        "header_names": sorted(str(name) for name in (definition.get("headers") or {})),
    }


def _sanitize_skill(definition: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": definition.get("slug"),
        "name": definition.get("name"),
        "description": definition.get("description") or "",
        "content": definition.get("content") or "",
    }


def build_harness_snapshot(
    *,
    agent_slug: str,
    version_number: int,
    config: AgentConfig,
    mcp_defs: list[dict[str, Any]],
    llm: dict[str, Any],
    max_steps: int,
    timeout_seconds: float,
    max_tokens: int,
    max_attempts: int,
    fallback_model: str | None,
    approval_mode: str,
    context_max_tokens: int,
    tool_output_max_chars: int,
    sub_agents: list[str],
) -> dict[str, Any]:
    return {
        "v": HARNESS_VERSION,
        "agent": {"slug": agent_slug, "version": version_number},
        "kind": config.kind,
        "plugin_name": config.plugin_name,
        "system_prompt": config.system_prompt,
        "tools": list(config.tools),
        "skills": [str(item.get("slug")) for item in config.skill_defs],
        "sub_agents": list(sub_agents),
        "tool_defs": [_sanitize_tool(item) for item in config.tool_defs],
        "skill_defs": [_sanitize_skill(item) for item in config.skill_defs],
        "mcp": [_sanitize_mcp(item) for item in mcp_defs],
        "llm": dict(llm),
        "limits": {
            "max_steps": max_steps,
            "timeout_seconds": timeout_seconds,
            "max_tokens": max_tokens,
            "max_attempts": max_attempts,
            "approval_mode": approval_mode,
        },
        "retry": {"fallback_model": fallback_model or None},
        "context": {
            "max_tokens": context_max_tokens,
            "tool_output_max_chars": tool_output_max_chars,
            "skills_mode": "index",
        },
    }


def harness_hash(snapshot: dict[str, Any]) -> str:
    canonical = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _item(field: str, left: Any, right: Any) -> HarnessDiffItem:
    return HarnessDiffItem(
        field=field, left=left, right=right, changed=left != right
    )


def diff_harness(
    left: RunOut,
    right: RunOut,
    left_snapshot: dict[str, Any] | None,
    right_snapshot: dict[str, Any] | None,
    left_digest: TrajectoryDigest,
    right_digest: TrajectoryDigest,
) -> list[HarnessDiffItem]:
    def value(snapshot: dict[str, Any] | None, path: tuple[str, ...]) -> Any:
        current: Any = snapshot
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def prompt_chars(snapshot: dict[str, Any] | None) -> int | None:
        if snapshot is None:
            return None
        return len(str(snapshot.get("system_prompt") or ""))

    def mcp_refs(snapshot: dict[str, Any] | None) -> list[str] | None:
        if snapshot is None:
            return None
        return [str(item.get("ref")) for item in snapshot.get("mcp") or []]

    pairs: list[tuple[str, Any, Any]] = [
        (
            "agent_version",
            left.agent_version,
            right.agent_version,
        ),
        ("harness_hash", left.harness_hash, right.harness_hash),
        (
            "model",
            value(left_snapshot, ("llm", "model")),
            value(right_snapshot, ("llm", "model")),
        ),
        (
            "base_url",
            value(left_snapshot, ("llm", "base_url")),
            value(right_snapshot, ("llm", "base_url")),
        ),
        (
            "max_steps",
            value(left_snapshot, ("limits", "max_steps")),
            value(right_snapshot, ("limits", "max_steps")),
        ),
        (
            "timeout_seconds",
            value(left_snapshot, ("limits", "timeout_seconds")),
            value(right_snapshot, ("limits", "timeout_seconds")),
        ),
        (
            "max_tokens",
            value(left_snapshot, ("limits", "max_tokens")),
            value(right_snapshot, ("limits", "max_tokens")),
        ),
        (
            "max_attempts",
            value(left_snapshot, ("limits", "max_attempts")),
            value(right_snapshot, ("limits", "max_attempts")),
        ),
        (
            "fallback_model",
            value(left_snapshot, ("retry", "fallback_model")),
            value(right_snapshot, ("retry", "fallback_model")),
        ),
        (
            "approval_mode",
            value(left_snapshot, ("limits", "approval_mode")),
            value(right_snapshot, ("limits", "approval_mode")),
        ),
        (
            "context_max_tokens",
            value(left_snapshot, ("context", "max_tokens")),
            value(right_snapshot, ("context", "max_tokens")),
        ),
        (
            "skills_mode",
            value(left_snapshot, ("context", "skills_mode")),
            value(right_snapshot, ("context", "skills_mode")),
        ),
        (
            "tools",
            value(left_snapshot, ("tools",)),
            value(right_snapshot, ("tools",)),
        ),
        (
            "skills",
            value(left_snapshot, ("skills",)),
            value(right_snapshot, ("skills",)),
        ),
        (
            "sub_agents",
            value(left_snapshot, ("sub_agents",)),
            value(right_snapshot, ("sub_agents",)),
        ),
        ("mcp", mcp_refs(left_snapshot), mcp_refs(right_snapshot)),
        ("prompt_chars", prompt_chars(left_snapshot), prompt_chars(right_snapshot)),
        ("status", left.status, right.status),
        ("steps", left_digest.steps, right_digest.steps),
        (
            "total_tool_calls",
            left_digest.total_tool_calls,
            right_digest.total_tool_calls,
        ),
        (
            "failed_tool_calls",
            left_digest.failed_tool_calls,
            right_digest.failed_tool_calls,
        ),
    ]
    return [_item(field, left_value, right_value) for field, left_value, right_value in pairs]
