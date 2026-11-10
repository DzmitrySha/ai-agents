"""Read-only preflight: is an agent ready to run right now?"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.execution import resolve_llm
from app.agents.mcp_client import list_remote_tools
from app.agents.plugins import get_plugin
from app.auth.principal import Principal
from app.repos import mcp_connections as mcp_connections_repo
from app.repos import skills as skills_repo
from app.repos.agents import get_version, resolve_agent
from app.repos.runs import count_runs_since, tokens_since
from app.repos.tools import definitions_for
from app.runtime.llm_config import fetch_models, project_llm
from app.runtime.manager import (
    _config_from_snapshot,
    resolve_approval_mode,
    resolve_limits,
    resolve_max_attempts,
    resolve_token_budget,
)
from app.runtime.models import (
    PreflightCheck,
    PreflightEffective,
    PreflightRequest,
    PreflightResult,
    utcnow,
)
from app.settings import get_settings

MCP_PREFLIGHT_TIMEOUT_SECONDS = 10.0
MCP_CALL_TIMEOUT_SECONDS = 12.0


async def _run_check(check_id: str, factory) -> PreflightCheck:
    try:
        return await factory()
    except Exception as exc:  # noqa: BLE001 - every check reports, none aborts preflight
        return PreflightCheck(
            id=check_id,  # type: ignore[arg-type]
            status="error",
            message=f"{type(exc).__name__}: {exc}",
        )


async def run_preflight(
    session: AsyncSession, p: Principal, request: PreflightRequest
) -> PreflightResult:
    agent = await resolve_agent(session, request.agent_id, p, for_run=True)
    version = await get_version(session, agent)
    if version is None:
        raise ValueError("agent is not published")

    config = _config_from_snapshot(dict(version.snapshot or {}))
    settings = get_settings()
    max_steps, timeout = resolve_limits(config.limits, settings)
    max_tokens = resolve_token_budget(config.limits, settings)
    max_attempts = resolve_max_attempts(config.limits, settings)
    approval_mode = resolve_approval_mode(config.limits, settings)
    llm = resolve_llm(config.llm, request.llm)
    live_tools = [str(name) for name in (agent.tools or [])]
    live_skills = [str(name) for name in (agent.skills or [])]
    mcp_refs = [name for name in live_tools if name.startswith("mcp:")]
    http_tools = [name for name in live_tools if not name.startswith("mcp:")]
    checks: list[PreflightCheck] = [
        PreflightCheck(
            id="agent",
            status="ok",
            message=f"published v{version.version}",
            details={"slug": agent.slug, "version": version.version},
        )
    ]

    async def check_plugin() -> PreflightCheck:
        if config.kind != "plugin":
            return PreflightCheck(
                id="plugin", status="skip", message="not a plugin agent"
            )
        get_plugin(config.plugin_name or "")
        return PreflightCheck(
            id="plugin",
            status="ok",
            message=f"plugin {config.plugin_name}",
        )

    plugin_check = await _run_check("plugin", check_plugin)
    checks.append(plugin_check)
    plugin_agent = config.kind == "plugin"

    async def check_quota() -> PreflightCheck:
        from app.routers.runs import _daily_limit, _daily_token_limit

        run_limit = _daily_limit(p)
        token_limit = _daily_token_limit(p)
        if run_limit is None and token_limit is None:
            return PreflightCheck(id="quota", status="ok", message="unlimited")
        since = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        parts: list[str] = []
        details: dict[str, Any] = {}
        errors: list[str] = []
        if run_limit is not None:
            used = await count_runs_since(
                session,
                principal_kind=p.kind,
                principal_id=p.id,
                since=since,
            )
            details.update({"used": used, "limit": run_limit})
            if used >= run_limit:
                errors.append(f"daily run quota exhausted ({used}/{run_limit})")
            else:
                parts.append(f"{run_limit - used} of {run_limit} runs left")
        if token_limit is not None:
            tokens_used = await tokens_since(
                session,
                principal_kind=p.kind,
                principal_id=p.id,
                since=since,
            )
            details.update({"tokens_used": tokens_used, "token_limit": token_limit})
            if tokens_used >= token_limit:
                errors.append(
                    f"daily token budget exhausted ({tokens_used}/{token_limit})"
                )
            else:
                parts.append(f"{token_limit - tokens_used} tokens left")
        if errors:
            return PreflightCheck(
                id="quota",
                status="error",
                message="; ".join(errors),
                details=details,
            )
        return PreflightCheck(
            id="quota",
            status="ok",
            message="; ".join(parts),
            details=details,
        )

    checks.append(await _run_check("quota", check_quota))

    async def check_tools() -> PreflightCheck:
        definitions = await definitions_for(session, http_tools)
        return PreflightCheck(
            id="tools",
            status="ok",
            message=f"{len(live_tools)} tools",
            details={"tools": live_tools, "custom_definitions": len(definitions)},
        )

    async def check_skills() -> PreflightCheck:
        rows = await skills_repo.resolve_skill_refs(session, live_skills)
        empty = [row.slug for row in rows if not (row.content or "").strip()]
        if empty:
            return PreflightCheck(
                id="skills",
                status="warn",
                message=f"empty skill body: {', '.join(empty)}",
                details={"skills": live_skills, "empty": empty},
            )
        return PreflightCheck(
            id="skills",
            status="ok",
            message=f"{len(rows)} skills",
            details={"skills": live_skills},
        )

    async def check_mcp() -> PreflightCheck:
        defs = await mcp_connections_repo.resolve_defs(session, mcp_refs)
        groups: dict[str, dict[str, Any]] = {}
        for item in defs:
            groups.setdefault(str(item["connection"]), item)
        listed: dict[str, set[str]] = {}
        for connection, item in groups.items():
            tools = await asyncio.wait_for(
                list_remote_tools(
                    str(item["url"]),
                    dict(item.get("headers") or {}),
                    min(float(item["timeout_seconds"]), MCP_PREFLIGHT_TIMEOUT_SECONDS),
                ),
                timeout=MCP_CALL_TIMEOUT_SECONDS,
            )
            listed[connection] = {str(tool["name"]) for tool in tools}
        missing = [
            item["ref"]
            for item in defs
            if str(item["tool"]) not in listed.get(str(item["connection"]), set())
        ]
        if missing:
            return PreflightCheck(
                id="mcp",
                status="error",
                message=f"tool not found: {', '.join(missing)}",
                details={"missing": missing},
            )
        return PreflightCheck(
            id="mcp",
            status="ok",
            message=f"{len(groups)} connections",
            details={"connections": sorted(groups)},
        )

    async def check_llm() -> PreflightCheck:
        api_key = (
            request.llm.api_key
            if request.llm is not None and request.llm.api_key
            else project_llm().api_key
        )
        models = await fetch_models(
            str(llm["base_url"] or ""),
            api_key,
            auth_type=llm["auth_type"],
            auth_header=llm["auth_header"],
            auth_prefix=llm["auth_prefix"],
        )
        model = str(llm["model"] or "")
        if model and model not in models:
            return PreflightCheck(
                id="llm",
                status="warn",
                message=f"model {model} is not listed",
                details={"model": model, "models": len(models)},
            )
        return PreflightCheck(
            id="llm",
            status="ok",
            message=f"{len(models)} models",
            details={"model": model, "models": len(models)},
        )

    if plugin_agent:
        for check_id in ("tools", "skills", "mcp", "llm"):
            checks.append(
                PreflightCheck(
                    id=check_id,  # type: ignore[arg-type]
                    status="skip",
                    message="plugin agents own their runtime",
                )
            )
    else:
        checks.append(await _run_check("tools", check_tools))
        checks.append(await _run_check("skills", check_skills))
        checks.append(await _run_check("mcp", check_mcp))
        checks.append(await _run_check("llm", check_llm))

    checks.append(
        PreflightCheck(
            id="limits",
            status="ok",
            message=f"max_steps={max_steps}, timeout={timeout:g}s, max_tokens={max_tokens}, max_attempts={max_attempts}, approval_mode={approval_mode}",
            details={
                "max_steps": max_steps,
                "timeout_seconds": timeout,
                "max_tokens": max_tokens,
                "max_attempts": max_attempts,
                "approval_mode": approval_mode,
            },
        )
    )

    return PreflightResult(
        ok=not any(check.status == "error" for check in checks),
        checks=checks,
        effective=PreflightEffective(
            agent_id=agent.slug,
            agent_version=version.version,
            model=llm["model"],
            base_url=llm["base_url"],
            max_steps=max_steps,
            timeout_seconds=timeout,
            max_tokens=max_tokens,
            max_attempts=max_attempts,
            approval_mode=approval_mode,
            sub_agents=list(config.sub_agents),
            tools=live_tools,
            skills=live_skills,
            mcp=mcp_refs,
        ),
    )
