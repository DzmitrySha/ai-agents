"""Run lifecycle: DB-backed status/events, live SSE fan-out, limits, cancel."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.agents.approval import APPROVAL_REJECTED_PREFIX, ApprovalDenied
from app.agents.execution import AgentConfig, resolve_llm, stream_agent
from app.auth.principal import Principal
from app.logging_setup import logger
from app.models import new_id
from app.redaction import redact_text
from app.repos import approvals as approvals_repo
from app.repos import mcp_connections as mcp_connections_repo
from app.repos import memory as memory_repo
from app.repos import skills as skills_repo
from app.repos import usage as usage_repo
from app.repos.agents import get_version, resolve_agent
from app.repos.errors import UnknownRefs
from app.repos.tools import definitions_for
from app.repos.runs import (
    IdempotencyConflict,
    append_run_event,
    assert_daily_token_budget,
    can_view_run,
    count_child_runs,
    count_queued_runs,
    create_run_row,
    get_agent_for_run,
    get_run_by_idempotency,
    get_run_row,
    load_run_events,
    max_event_seq,
    prompt_for,
    set_run_status,
    to_out,
)
from app.runtime.digest import build_digest
from app.runtime.delivery import enqueue_for_run
from app.runtime.approvals import ApprovalGate
from app.runtime.failures import (
    classify_failure,
    failure_is_retryable,
    redacted_error,
)
from app.runtime.models import (
    TERMINAL_STATUSES,
    CreateRunRequest,
    LLMConfig,
    RunEvent,
    RunOut,
    RunStatus,
)
from app.runtime.harness import build_harness_snapshot, harness_hash
from app.runtime.store import LiveHub
from app.settings import Settings, get_settings


def _config_from_snapshot(snapshot: dict[str, Any]) -> AgentConfig:
    return AgentConfig(
        kind=str(snapshot.get("kind") or "preset"),
        plugin_name=snapshot.get("plugin_name"),
        system_prompt=str(snapshot.get("system_prompt") or ""),
        tools=[str(name) for name in snapshot.get("tools") or []],
        llm=dict(snapshot.get("llm") or {}),
        limits=dict(snapshot.get("limits") or {}),
        tool_defs=[dict(item) for item in snapshot.get("tool_defs") or []],
        skill_defs=[dict(item) for item in snapshot.get("skill_defs") or []],
        sub_agents=[str(name) for name in snapshot.get("sub_agents") or []],
    )


def resolve_limits(
    agent_limits: dict[str, Any], settings: Settings
) -> tuple[int, float]:
    try:
        steps = int(agent_limits.get("max_steps") or settings.max_steps)
    except (TypeError, ValueError):
        steps = settings.max_steps
    try:
        timeout = float(
            agent_limits.get("timeout_seconds") or settings.run_timeout_seconds
        )
    except (TypeError, ValueError):
        timeout = settings.run_timeout_seconds
    return (
        max(1, min(steps, settings.max_steps_cap)),
        max(1.0, min(timeout, settings.run_timeout_cap_seconds)),
    )


def resolve_token_budget(agent_limits: dict[str, Any], settings: Settings) -> int:
    raw = agent_limits.get("max_tokens")
    if isinstance(raw, bool):
        raw = None
    try:
        budget = int(raw or settings.run_token_budget)
    except (TypeError, ValueError):
        budget = settings.run_token_budget
    return max(1, min(budget, settings.run_token_cap))


def resolve_max_attempts(agent_limits: dict[str, Any], settings: Settings) -> int:
    raw = agent_limits.get("max_attempts")
    if isinstance(raw, bool):
        raw = None
    try:
        attempts = int(raw or settings.run_max_attempts)
    except (TypeError, ValueError):
        attempts = settings.run_max_attempts
    return max(1, min(attempts, settings.run_max_attempts_cap))


def resolve_approval_mode(agent_limits: dict[str, Any], settings: Settings) -> str:
    raw = str(agent_limits.get("approval_mode") or settings.run_approval_mode)
    return raw if raw in {"never", "mutating", "all"} else "mutating"


def principal_daily_limits(
    p: Principal, settings: Settings
) -> tuple[int | None, int | None]:
    if p.is_superadmin or p.app_role != "user":
        return None, None
    run_limit = p.daily_run_limit
    if run_limit is None:
        run_limit = settings.user_daily_run_limit
    return run_limit or None, settings.user_daily_token_limit or None


def _attempt_override(
    run_override: LLMConfig | None, fallback_model: str | None, attempt: int
) -> LLMConfig | None:
    if not fallback_model or attempt <= 1:
        return run_override
    base = run_override.model_dump(exclude_none=True) if run_override else {}
    base["model"] = fallback_model
    return LLMConfig(**base)


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {str(key): _redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


class StepLimitExceeded(Exception):
    """Raised when a run exceeds its agent step limit."""


class QueueFull(Exception):
    """Raised when the soft queued-run cap is reached."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"run queue is full ({limit})")


class TokenBudgetExceeded(Exception):
    """Raised when a run consumes more tokens than its per-run budget."""


class RunGate:
    """In-process bounded concurrency (single backend replica).

    Slots are held only while `_execute` is running; queued runs keep their
    Postgres row in `queued` status until a slot is acquired.
    """

    def __init__(self, total: int, per_agent: int) -> None:
        self.total = total
        self.per_agent = per_agent
        self.running = 0
        self.by_agent: dict[str, int] = {}
        self._condition = asyncio.Condition()

    async def acquire(self, slug: str) -> None:
        async with self._condition:
            while (
                self.running >= self.total
                or self.by_agent.get(slug, 0) >= self.per_agent
            ):
                await self._condition.wait()
            self.running += 1
            self.by_agent[slug] = self.by_agent.get(slug, 0) + 1

    async def release(self, slug: str) -> None:
        async with self._condition:
            self.running = max(0, self.running - 1)
            current = self.by_agent.get(slug, 0)
            if current <= 1:
                self.by_agent.pop(slug, None)
            else:
                self.by_agent[slug] = current - 1
            self._condition.notify_all()


class RunManager:
    def __init__(self, hub: LiveHub, settings: Settings | None = None) -> None:
        self.hub = hub
        self._settings = settings or get_settings()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._done: dict[str, asyncio.Future[None]] = {}
        self._seq: dict[str, int] = {}
        self._seq_lock = asyncio.Lock()
        self._gate = RunGate(
            self._settings.run_max_concurrency,
            self._settings.run_max_concurrency_per_agent,
        )
        self._approvals = ApprovalGate()

    def gate_snapshot(self) -> dict[str, Any]:
        return {
            "running": self._gate.running,
            "total": self._gate.total,
            "per_agent": dict(self._gate.by_agent),
            "approvals_pending": len(self._approvals._pending),
        }

    async def _alloc_seq(self, session_factory, run_id: str) -> int:
        async with self._seq_lock:
            if run_id not in self._seq:
                async with session_factory() as session:
                    self._seq[run_id] = await max_event_seq(session, run_id)
            self._seq[run_id] += 1
            return self._seq[run_id]

    async def _emit(
        self, session_factory, run_id: str, event: str, data: dict[str, Any]
    ) -> None:
        seq = await self._alloc_seq(session_factory, run_id)
        async with session_factory() as session:
            await append_run_event(session, run_id, seq, event, data)
        await self.hub.publish(run_id, RunEvent(seq=seq, event=event, data=data))

    def _limits(self, agent_limits: dict[str, Any]) -> tuple[int, float]:
        return resolve_limits(agent_limits, self._settings)

    async def create_run(
        self,
        session_factory,
        p: Principal,
        request: CreateRunRequest,
        *,
        daily_limit: int | None = None,
        daily_token_limit: int | None = None,
        idempotency_key: str | None = None,
        parent_run_id: str | None = None,
        depth: int = 0,
    ) -> RunOut:
        async with session_factory() as session:
            if idempotency_key:
                existing = await get_run_by_idempotency(
                    session,
                    principal_kind=p.kind,
                    principal_id=p.id,
                    key=idempotency_key,
                )
                if existing is not None:
                    return await to_out(session, existing)
            agent = await resolve_agent(session, request.agent_id, p, for_run=True)
            version = await get_version(session, agent)
            if version is None:
                raise ValueError("agent is not published")
            queued = await count_queued_runs(session)
            if queued >= self._settings.run_max_queued:
                raise QueueFull(self._settings.run_max_queued)
            snapshot = dict(version.snapshot or {})
            # Tools and skills are live: body edits apply on the next run without republish.
            # Snapshot still stores defs for history; system_prompt/llm/limits come from it.
            live_tools = [str(name) for name in (agent.tools or [])]
            live_skills = [str(name) for name in (agent.skills or [])]
            http_tools = [name for name in live_tools if not name.startswith("mcp:")]
            mcp_refs = [name for name in live_tools if name.startswith("mcp:")]
            try:
                tool_defs = await definitions_for(session, http_tools)
                skill_rows = await skills_repo.resolve_skill_refs(session, live_skills)
            except UnknownRefs as exc:
                raise ValueError(str(exc)) from exc
            skill_defs = [skills_repo.skill_definition(row) for row in skill_rows]
            mcp_defs = await mcp_connections_repo.resolve_defs(session, mcp_refs)

            config = replace(
                _config_from_snapshot(snapshot),
                tools=live_tools,
                tool_defs=tool_defs,
                skill_defs=skill_defs,
                mcp_defs=mcp_defs,
                memory_enabled=bool(agent.memory_enabled),
            )
            max_steps, timeout = resolve_limits(config.limits, self._settings)
            token_budget = resolve_token_budget(config.limits, self._settings)
            max_attempts = resolve_max_attempts(config.limits, self._settings)
            approval_mode = resolve_approval_mode(config.limits, self._settings)
            fallback_model = (self._settings.run_fallback_model or "").strip() or None
            if daily_token_limit is not None:
                await assert_daily_token_budget(
                    session, p=p, limit=daily_token_limit
                )
            harness = build_harness_snapshot(
                agent_slug=agent.slug,
                version_number=version.version,
                config=config,
                mcp_defs=mcp_defs,
                llm=resolve_llm(config.llm, request.llm),
                max_steps=max_steps,
                timeout_seconds=timeout,
                max_tokens=token_budget,
                max_attempts=max_attempts,
                fallback_model=fallback_model,
                approval_mode=approval_mode,
                context_max_tokens=self._settings.run_context_max_tokens,
                tool_output_max_chars=self._settings.run_tool_output_max_chars,
                sub_agents=config.sub_agents,
            )
            try:
                row = await create_run_row(
                    session,
                    agent=agent,
                    version=version,
                    p=p,
                    request=request,
                    daily_limit=daily_limit,
                    harness_snapshot=harness,
                    harness_hash=harness_hash(harness),
                    idempotency_key=idempotency_key,
                    parent_run_id=parent_run_id,
                    depth=depth,
                )
            except IntegrityError:
                await session.rollback()
                if idempotency_key:
                    existing = await get_run_by_idempotency(
                        session,
                        principal_kind=p.kind,
                        principal_id=p.id,
                        key=idempotency_key,
                    )
                    if existing is not None:
                        raise IdempotencyConflict(existing.id) from None
                raise
            out = await to_out(session, row)
            run_id = row.id
            slug = agent.slug
            agent_id = agent.id
            version_number = version.version

        self._seq[run_id] = 0
        self._done[run_id] = asyncio.get_running_loop().create_future()
        task_factory = (
            self._run_with_slot if parent_run_id is None else self._run_direct
        )
        task = asyncio.create_task(
            task_factory(
                session_factory,
                run_id=run_id,
                slug=slug,
                agent_id=agent_id,
                version_number=version_number,
                config=config,
                prompt=prompt_for(request),
                run_override=request.llm,
                max_steps=max_steps,
                timeout=timeout,
                token_budget=token_budget,
                max_attempts=max_attempts,
                fallback_model=fallback_model,
                approval_mode=approval_mode,
                principal=p,
                depth=depth,
            )
        )
        self._tasks[run_id] = task

        def _settle(_t, rid=run_id):
            self._tasks.pop(rid, None)
            fut = self._done.pop(rid, None)
            if fut is not None and not fut.done():
                fut.set_result(None)

        task.add_done_callback(_settle)
        return out

    async def _run_with_slot(
        self,
        session_factory,
        *,
        run_id: str,
        slug: str,
        **kwargs: Any,
    ) -> None:
        acquired = False
        try:
            await self._gate.acquire(slug)
            acquired = True
            async with session_factory() as session:
                row = await get_run_row(session, run_id)
            if row is None or row.status in TERMINAL_STATUSES:
                return
            await self._execute(
                session_factory,
                run_id=run_id,
                slug=slug,
                **kwargs,
            )
        finally:
            if acquired:
                await self._gate.release(slug)
            self._seq.pop(run_id, None)

    async def _run_direct(
        self,
        session_factory,
        *,
        run_id: str,
        slug: str,
        **kwargs: Any,
    ) -> None:
        try:
            async with session_factory() as session:
                row = await get_run_row(session, run_id)
            if row is None or row.status in TERMINAL_STATUSES:
                return
            await self._execute(
                session_factory,
                run_id=run_id,
                slug=slug,
                **kwargs,
            )
        finally:
            self._seq.pop(run_id, None)

    async def wait_completed(self, run_id: str) -> None:
        """Block until the run reaches a terminal state (no-op for unknown runs)."""
        fut = self._done.get(run_id)
        if fut is None:
            return
        await fut

    async def cancel_run(
        self, session_factory, run_id: str, p: Principal
    ) -> RunOut | None:
        async with session_factory() as session:
            row = await get_run_row(session, run_id)
            if row is None:
                return None
            agent = await get_agent_for_run(session, row)
            if not can_view_run(row, agent, p):
                return None
            if not (
                p.is_superadmin
                or (row.principal_kind == p.kind and row.principal_id == p.id)
            ):
                return None
            if row.status in TERMINAL_STATUSES:
                return await to_out(session, row)
            await set_run_status(
                session,
                run_id,
                RunStatus.cancelled,
                failure_kind="cancelled",
            )
        async with session_factory() as session:
            await approvals_repo.expire_pending(session, run_id, resolved_by="cancel")
        self._approvals.cancel_run(run_id)
        await self._emit(session_factory, run_id, "run.cancelled", {})
        await enqueue_for_run(session_factory, run_id)
        task = self._tasks.get(run_id)
        if task is not None:
            task.cancel()
        async with session_factory() as session:
            row = await get_run_row(session, run_id)
            return await to_out(session, row) if row is not None else None

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        for fut in self._done.values():
            if not fut.done():
                fut.cancel()
        self._done.clear()

    async def _request_approval(
        self,
        session_factory,
        run_id: str,
        tool: str,
        tool_input: dict[str, Any],
    ) -> bool:
        approval_id = new_id()
        safe_input = _redact_value(tool_input)
        future = self._approvals.register(run_id, approval_id)
        try:
            async with session_factory() as session:
                await approvals_repo.create_approval(
                    session,
                    approval_id=approval_id,
                    run_id=run_id,
                    tool=tool,
                    tool_input=safe_input,
                )
                current = await get_run_row(session, run_id)
                if current is None or current.status in TERMINAL_STATUSES:
                    await approvals_repo.resolve_approval(
                        session,
                        approval_id,
                        status="expired",
                        resolved_by="system",
                    )
                    raise ApprovalDenied("run is no longer active")
                await set_run_status(session, run_id, RunStatus.waiting_approval)
            await self._emit(
                session_factory,
                run_id,
                "run.approval_required",
                {
                    "approval_id": approval_id,
                    "tool": tool,
                    "input": safe_input,
                    "timeout_seconds": self._settings.run_approval_timeout_seconds,
                },
            )
            try:
                approved = await self._approvals.wait(
                    future, self._settings.run_approval_timeout_seconds
                )
            except ApprovalDenied:
                async with session_factory() as session:
                    current = await approvals_repo.get_approval(session, approval_id)
                    if current is not None and current.status == "pending":
                        await approvals_repo.resolve_approval(
                            session,
                            approval_id,
                            status="expired",
                            resolved_by="timeout",
                        )
                await self._emit(
                    session_factory,
                    run_id,
                    "run.approval_resolved",
                    {"approval_id": approval_id, "decision": "expired"},
                )
                raise
            if not approved:
                raise ApprovalDenied(f"{tool} rejected")
            return True
        finally:
            self._approvals.unregister(run_id, approval_id)

    async def resolve_approval(
        self,
        session_factory,
        run_id: str,
        approval_id: str,
        *,
        approved: bool,
        resolved_by: str,
    ):
        async with session_factory() as session:
            row = await approvals_repo.get_approval(session, approval_id)
            if (
                row is None
                or row.run_id != run_id
                or row.status != "pending"
            ):
                return None
            run = await get_run_row(session, run_id)
            if run is None:
                return None
            decision = "approved" if approved else "rejected"
            row = await approvals_repo.resolve_approval(
                session,
                approval_id,
                status=decision,
                resolved_by=resolved_by,
            )
            if run.status == RunStatus.waiting_approval.value:
                await set_run_status(session, run_id, RunStatus.running)
        await self._emit(
            session_factory,
            run_id,
            "run.approval_resolved",
            {"approval_id": approval_id, "decision": decision},
        )
        self._approvals.resolve(approval_id, approved)
        return row

    async def _run_subagent(
        self,
        session_factory,
        *,
        parent_run_id: str,
        parent_agent: str,
        depth: int,
        principal: Principal,
        agent_slug: str,
        prompt: str,
    ) -> str:
        if depth + 1 > self._settings.run_max_subrun_depth:
            return (
                "error: subrun depth limit exceeded "
                f"({depth + 1} > {self._settings.run_max_subrun_depth})"
            )
        async with session_factory() as session:
            children = await count_child_runs(session, parent_run_id)
        if children >= self._settings.run_max_subruns_per_run:
            return (
                "error: subrun count limit exceeded "
                f"({children}/{self._settings.run_max_subruns_per_run})"
            )
        run_limit, token_limit = principal_daily_limits(
            principal, self._settings
        )
        try:
            child = await self.create_run(
                session_factory,
                principal,
                CreateRunRequest(agent_id=agent_slug, input=prompt),
                daily_limit=run_limit,
                daily_token_limit=token_limit,
                parent_run_id=parent_run_id,
                depth=depth + 1,
            )
        except Exception as exc:  # noqa: BLE001 - report to the calling model
            return "error: " + redact_text(f"{type(exc).__name__}: {exc}")
        await self._emit(
            session_factory,
            parent_run_id,
            "subrun.started",
            {"run_id": child.run_id, "agent_id": agent_slug},
        )
        await self.wait_completed(child.run_id)
        async with session_factory() as session:
            row = await get_run_row(session, child.run_id)
        status = row.status if row is not None else "failed"
        await self._emit(
            session_factory,
            parent_run_id,
            "subrun.completed",
            {
                "run_id": child.run_id,
                "agent_id": agent_slug,
                "status": status,
            },
        )
        if row is not None and row.status == RunStatus.succeeded.value:
            return row.output or "error: empty subrun output"
        return "error: subrun failed: " + (
            (row.error if row is not None else "run not found") or status
        )

    async def _memory_op(
        self,
        session_factory,
        *,
        run_id: str | None = None,
        agent_id: str,
        agent_slug: str,
        principal: Principal,
        operation: str,
        payload: dict[str, Any],
    ) -> str:
        try:
            async with session_factory() as session:
                if operation == "write":
                    row = await memory_repo.write(
                        session,
                        agent_id=agent_id,
                        principal_kind=principal.kind,
                        principal_id=principal.id,
                        namespace=agent_slug,
                        key=str(payload.get("key") or ""),
                        content=redact_text(str(payload.get("content") or "")),
                        tags=[
                            redact_text(str(tag))
                            for tag in payload.get("tags") or []
                        ],
                    )
                    if run_id:
                        await self._emit(
                            session_factory,
                            run_id,
                            "memory.write",
                            {"key": row.key, "namespace": row.namespace},
                        )
                    return f"stored {row.key}"
                if operation == "search":
                    rows = await memory_repo.search(
                        session,
                        agent_id=agent_id,
                        principal_kind=principal.kind,
                        principal_id=principal.id,
                        namespace=agent_slug,
                        query=str(payload.get("query") or ""),
                        limit=int(payload.get("limit") or 5),
                    )
                    return json.dumps(
                        [
                            {
                                "key": row.key,
                                "content": row.content,
                                "tags": list(row.tags or []),
                            }
                            for row in rows
                        ],
                        ensure_ascii=False,
                    )
                if operation == "delete":
                    removed = await memory_repo.delete_key(
                        session,
                        agent_id=agent_id,
                        principal_kind=principal.kind,
                        principal_id=principal.id,
                        namespace=agent_slug,
                        key=str(payload.get("key") or ""),
                    )
                    return "deleted" if removed else "error: memory not found"
                return f"error: unknown memory operation {operation}"
        except Exception as exc:  # noqa: BLE001 - report memory errors as text
            return "error: " + redact_text(f"{type(exc).__name__}: {exc}")

    async def _execute(
        self,
        session_factory,
        *,
        run_id: str,
        slug: str,
        agent_id: str,
        version_number: int,
        config: AgentConfig,
        prompt: str,
        run_override,
        max_steps: int,
        timeout: float,
        token_budget: int,
        max_attempts: int,
        fallback_model: str | None,
        approval_mode: str,
        principal: Principal,
        depth: int = 0,
    ) -> None:
        output_parts: list[str] = []
        steps = 0
        attempts = 0
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        has_usage = False
        try:
            async with session_factory() as session:
                await set_run_status(session, run_id, RunStatus.running)
            await self._emit(
                session_factory,
                run_id,
                "run.started",
                {"agent_id": slug, "agent_version": version_number},
            )

            async def approval_hook(tool_name: str, tool_input: dict[str, Any]) -> None:
                await self._request_approval(
                    session_factory, run_id, tool_name, tool_input
                )

            async def subrun_hook(agent_slug: str, prompt: str) -> str:
                return await self._run_subagent(
                    session_factory,
                    parent_run_id=run_id,
                    parent_agent=slug,
                    depth=depth,
                    principal=principal,
                    agent_slug=agent_slug,
                    prompt=prompt,
                )

            async def memory_hook(operation: str, payload: dict[str, Any]) -> str:
                return await self._memory_op(
                    session_factory,
                    run_id=run_id,
                    agent_id=agent_id,
                    agent_slug=slug,
                    principal=principal,
                    operation=operation,
                    payload=payload,
                )

            run_config = replace(
                config,
                approval_mode=approval_mode,
                approval_hook=approval_hook if approval_mode != "never" else None,
                subrun_hook=subrun_hook if config.sub_agents else None,
                memory_hook=memory_hook if config.memory_enabled else None,
            )

            try:
                async with asyncio.timeout(timeout):
                    attempt = 1
                    while True:
                        attempts = attempt
                        attempt_tool_calls = 0
                        output_parts.clear()
                        attempt_override = _attempt_override(
                            run_override, fallback_model, attempt
                        )
                        try:
                            async for event in stream_agent(
                                run_config, prompt, attempt_override, max_steps
                            ):
                                if event.type == "message.delta":
                                    delta = event.data.get("delta")
                                    if isinstance(delta, str):
                                        output_parts.append(delta)
                                await self._emit(
                                    session_factory, run_id, event.type, event.data
                                )
                                if event.type == "tool.result":
                                    output = event.data.get("output")
                                    if isinstance(
                                        output, str
                                    ) and output.startswith(APPROVAL_REJECTED_PREFIX):
                                        raise ApprovalDenied(
                                            output[len(APPROVAL_REJECTED_PREFIX) :].strip()
                                        )
                                if event.type == "token.usage":
                                    for key in (
                                        "prompt_tokens",
                                        "completion_tokens",
                                        "total_tokens",
                                    ):
                                        value = event.data.get(key)
                                        if (
                                            isinstance(value, int)
                                            and not isinstance(value, bool)
                                            and value >= 0
                                        ):
                                            usage[key] += value
                                    has_usage = True
                                    if usage["total_tokens"] > token_budget:
                                        raise TokenBudgetExceeded(
                                            "token budget exceeded "
                                            f"({usage['total_tokens']} > {token_budget})"
                                        )
                                if event.type == "tool.call":
                                    attempt_tool_calls += 1
                                    tool_name = event.data.get("tool")
                                    if isinstance(tool_name, str) and tool_name:
                                        usage_repo.spawn(
                                            session_factory,
                                            kind="tool",
                                            tool_slug=tool_name,
                                            agent_slug=slug,
                                            run_id=run_id,
                                            principal_kind=principal.kind,
                                            principal_id=principal.id,
                                        )
                                if event.type == "agent.step":
                                    steps += 1
                                    if steps > max_steps:
                                        raise StepLimitExceeded(
                                            f"max_steps limit exceeded ({max_steps})"
                                        )
                        except asyncio.CancelledError:
                            raise
                        except ApprovalDenied as exc:
                            await self._fail(
                                session_factory,
                                run_id,
                                str(exc),
                                failure_kind="approval_rejected",
                                attempts=attempts,
                                usage=usage if has_usage else None,
                            )
                            return
                        except TokenBudgetExceeded as exc:
                            await self._fail(
                                session_factory,
                                run_id,
                                str(exc),
                                failure_kind="token_budget",
                                attempts=attempts,
                                usage=usage if has_usage else None,
                            )
                            return
                        except StepLimitExceeded as exc:
                            await self._fail(
                                session_factory,
                                run_id,
                                str(exc),
                                failure_kind="step_limit",
                                attempts=attempts,
                                usage=usage if has_usage else None,
                            )
                            return
                        except Exception as exc:  # noqa: BLE001 - classify and maybe retry
                            failure_kind = classify_failure(
                                exc, tool_calls=attempt_tool_calls
                            )
                            if (
                                attempt < max_attempts
                                and failure_is_retryable(
                                    failure_kind, tool_calls=attempt_tool_calls
                                )
                            ):
                                delay = min(
                                    self._settings.run_retry_backoff_seconds
                                    * (2 ** (attempt - 1)),
                                    self._settings.run_retry_backoff_max_seconds,
                                )
                                next_attempt = attempt + 1
                                next_model = (
                                    fallback_model
                                    if fallback_model and next_attempt > 1
                                    else None
                                )
                                await self._emit(
                                    session_factory,
                                    run_id,
                                    "run.retry",
                                    {
                                        "attempt": next_attempt,
                                        "max_attempts": max_attempts,
                                        "failure_kind": failure_kind,
                                        "error": redacted_error(exc),
                                        "delay_seconds": delay,
                                        "model": next_model,
                                    },
                                )
                                await asyncio.sleep(delay)
                                attempt = next_attempt
                                continue
                            await self._fail(
                                session_factory,
                                run_id,
                                redacted_error(exc),
                                failure_kind=failure_kind,
                                attempts=attempts,
                                usage=usage if has_usage else None,
                            )
                            return

                        output = "".join(output_parts).strip()
                        await self._finish(
                            session_factory,
                            run_id,
                            RunStatus.succeeded,
                            "run.completed",
                            {"output": output},
                            output=output,
                            usage=usage if has_usage else None,
                            attempts=attempts,
                        )
                        return
            except TimeoutError:
                message = f"run timed out after {timeout:g}s"
                await self._fail(
                    session_factory,
                    run_id,
                    message,
                    failure_kind="timeout",
                    attempts=attempts or 1,
                    usage=usage if has_usage else None,
                )
            except Exception as exc:  # noqa: BLE001 - setup/emit failure
                await self._fail(
                    session_factory,
                    run_id,
                    redacted_error(exc),
                    failure_kind=classify_failure(exc),
                    attempts=attempts or 1,
                    usage=usage if has_usage else None,
                )
        except asyncio.CancelledError:
            async with session_factory() as session:
                row = await get_run_row(session, run_id)
            if row is not None and row.status not in TERMINAL_STATUSES:
                await self._finish(
                    session_factory,
                    run_id,
                    RunStatus.cancelled,
                    "run.cancelled",
                    {},
                    usage=usage if has_usage else None,
                    failure_kind="cancelled",
                    attempts=attempts or None,
                )
            elif has_usage:
                await self._store_usage(session_factory, run_id, usage)
            raise
        finally:
            await self.hub.close(run_id)
            self._seq.pop(run_id, None)

    async def _finish(
        self,
        session_factory,
        run_id: str,
        status: RunStatus,
        event: str,
        data: dict[str, Any],
        *,
        output: str | None = None,
        error: str | None = None,
        usage: dict[str, int] | None = None,
        failure_kind: str | None = None,
        attempts: int | None = None,
    ) -> None:
        """Статус и терминальное событие пишутся одной транзакцией.

        Иначе при shutdown/падении между двумя коммитами в истории остаётся
        succeeded без run.completed, и SSE-реплей «висит» без финала.
        """
        seq = await self._alloc_seq(session_factory, run_id)
        async with session_factory() as session:
            await set_run_status(
                session,
                run_id,
                status,
                output=output,
                error=error,
                prompt_tokens=usage["prompt_tokens"] if usage else None,
                completion_tokens=usage["completion_tokens"] if usage else None,
                total_tokens=usage["total_tokens"] if usage else None,
                failure_kind=failure_kind,
                attempts=attempts,
                commit=False,
            )
            await append_run_event(
                session, run_id, seq, event, data, commit=False
            )
            await session.commit()
        await self.hub.publish(run_id, RunEvent(seq=seq, event=event, data=data))
        await self._store_digest(session_factory, run_id)
        await enqueue_for_run(session_factory, run_id)

    async def _store_usage(
        self, session_factory, run_id: str, usage: dict[str, int]
    ) -> None:
        try:
            async with session_factory() as session:
                row = await get_run_row(session, run_id)
                if row is None:
                    return
                row.prompt_tokens = usage["prompt_tokens"]
                row.completion_tokens = usage["completion_tokens"]
                row.total_tokens = usage["total_tokens"]
                await session.commit()
        except Exception as exc:  # noqa: BLE001 - never mask cancellation
            logger.warning("usage store failed: {}", exc)

    async def _store_digest(self, session_factory, run_id: str) -> None:
        try:
            async with session_factory() as session:
                row = await get_run_row(session, run_id)
                if row is None:
                    return
                events = await load_run_events(session, run_id)
                row.digest = build_digest(row, events)
                await session.commit()
        except Exception as exc:  # noqa: BLE001 - digest is best-effort
            logger.warning("digest store failed: {}", exc)

    async def _fail(
        self,
        session_factory,
        run_id: str,
        message: str,
        *,
        usage: dict[str, int] | None = None,
        failure_kind: str = "internal",
        attempts: int | None = None,
    ) -> None:
        async with session_factory() as session:
            current = await get_run_row(session, run_id)
            if current is not None and current.status in TERMINAL_STATUSES:
                return
        message = redact_text(message)
        await self._finish(
            session_factory,
            run_id,
            RunStatus.failed,
            "run.failed",
            {"error": message},
            error=message,
            usage=usage,
            failure_kind=failure_kind,
            attempts=attempts,
        )
