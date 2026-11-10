"""Preset/plugin execution: LangGraph ReAct agent and graph-event translation."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import BaseMessage, trim_messages
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.tools import BaseTool, StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from app.agents.approval import ApprovalTool
from app.agents.custom_http import build_tool
from app.agents.events import AgentEvent
from app.agents.mcp_client import build_mcp_tools
from app.agents.plugins import get_plugin
from app.agents.tools import TOOLS
from app.runtime.llm_config import auth_headers, project_llm
from app.runtime.models import LLMConfig
from app.settings import Settings, get_settings


@dataclass(frozen=True)
class AgentConfig:
    kind: str
    plugin_name: str | None
    system_prompt: str
    tools: list[str]
    llm: dict[str, Any]
    limits: dict[str, Any]
    tool_defs: list[dict[str, Any]] = field(default_factory=list)
    skill_defs: list[dict[str, Any]] = field(default_factory=list)
    mcp_defs: list[dict[str, Any]] = field(default_factory=list)
    sub_agents: list[str] = field(default_factory=list)
    subrun_hook: Any = None
    memory_enabled: bool = False
    memory_hook: Any = None
    approval_mode: str = "never"
    approval_hook: Any = None


def resolve_llm(
    agent_llm: dict[str, Any], run_override: LLMConfig | None
) -> dict[str, Any]:
    """Effective LLM settings without secrets (safe for snapshots/logs)."""
    project = project_llm()
    override = run_override or LLMConfig()
    temperature = agent_llm.get("temperature")
    auth_type = override.auth_type or project.auth_type
    api_key = (override.api_key or project.api_key or "").strip()
    return {
        "model": override.model or agent_llm.get("model") or project.model,
        "base_url": override.base_url or agent_llm.get("base_url") or project.base_url,
        "temperature": temperature if isinstance(temperature, (int, float)) else 0.2,
        "auth_type": auth_type,
        "auth_header": override.auth_header or project.auth_header,
        "auth_prefix": (
            override.auth_prefix
            if override.auth_prefix is not None
            else project.auth_prefix
        ),
        "api_key_present": bool(
            api_key and api_key.lower() not in {"not-needed", "none"}
            and (auth_type or "bearer") != "none"
        ),
    }


def build_llm(agent_llm: dict[str, Any], run_override: LLMConfig | None) -> ChatOpenAI:
    resolved = resolve_llm(agent_llm, run_override)
    project = project_llm()
    override = run_override or LLMConfig()
    # Токен уходит ровно в тот заголовок/с префиксом, который настроен у провайдера;
    # `api_key` SDK — заглушка, реальный заголовок задаётся через default_headers.
    headers = auth_headers(
        override.api_key or project.api_key,
        override.auth_type or project.auth_type,
        override.auth_header or project.auth_header,
        override.auth_prefix
        if override.auth_prefix is not None
        else project.auth_prefix,
    )
    return ChatOpenAI(
        model=resolved["model"],
        base_url=resolved["base_url"],
        api_key="not-needed",
        default_headers=headers or None,
        temperature=resolved["temperature"],
        streaming=True,
        stream_usage=True,
    )


def _text(content: Any) -> str:
    """Normalize LLM chunk content (str | list of content blocks) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return ""


def _tool_output_text(output: Any) -> str:
    content = getattr(output, "content", output)
    return content if isinstance(content, str) else _text(content)


def _as_nonnegative_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _usage_from_output(output: Any) -> dict[str, int] | None:
    """Extract token usage from LangChain's AIMessage or raw response metadata."""
    usage_metadata = getattr(output, "usage_metadata", None)
    response_metadata = getattr(output, "response_metadata", None) or {}
    prompt = completion = total = None
    if isinstance(usage_metadata, dict):
        prompt = _as_nonnegative_int(usage_metadata.get("input_tokens"))
        completion = _as_nonnegative_int(usage_metadata.get("output_tokens"))
        total = _as_nonnegative_int(usage_metadata.get("total_tokens"))
    if prompt is None and completion is None and total is None:
        token_usage = (
            response_metadata.get("token_usage")
            if isinstance(response_metadata, dict)
            else None
        )
        if not isinstance(token_usage, dict):
            return None
        prompt = _as_nonnegative_int(token_usage.get("prompt_tokens"))
        completion = _as_nonnegative_int(token_usage.get("completion_tokens"))
        total = _as_nonnegative_int(token_usage.get("total_tokens"))
    if prompt is None and completion is None and total is None:
        return None
    prompt = prompt or 0
    completion = completion or 0
    total = total or (prompt + completion)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def configure_langfuse(settings: Settings | None = None) -> None:
    """Register the Langfuse singleton once per process (v3 CallbackHandler needs it)."""
    settings = settings or get_settings()
    if not settings.langfuse_enabled:
        return
    os.environ["LANGFUSE_HOST"] = settings.langfuse_host
    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
    os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key

    from langfuse import Langfuse

    Langfuse(
        host=settings.langfuse_host,
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
    )


def _langfuse_callback() -> Any:
    from langfuse.langchain import CallbackHandler

    return CallbackHandler(public_key=get_settings().langfuse_public_key)


def _agent_tools(
    names: list[str],
    definitions: list[dict[str, Any]] | None = None,
    *,
    approval_hook: Any = None,
    approval_mode: str = "never",
) -> list[BaseTool]:
    custom = {str(item["slug"]): item for item in definitions or []}
    tools: list[BaseTool] = []
    for name in names:
        if name.startswith("mcp:"):
            # External MCP tools are built by `build_mcp_tools` (needs a live session).
            continue
        tool_obj = TOOLS.get(name)
        definition = None
        if tool_obj is None:
            definition = custom.get(name)
            if definition is None:
                raise RuntimeError(f"unknown tool: {name}")
            tool_obj = build_tool(definition)
        mutating = bool(
            definition
            and str(definition.get("method") or "GET").upper()
            not in {"GET", "HEAD", "OPTIONS"}
        )
        if approval_hook is not None and (
            approval_mode == "all" or (approval_mode == "mutating" and mutating)
        ):
            tool_obj = ApprovalTool.wrap(tool_obj, approval_hook)
        tools.append(tool_obj)
    return tools


SKILL_HEADER = "# Skills (procedural knowledge)"


def _skill_limit() -> int:
    return get_settings().run_tool_output_max_chars


class LoadSkillArgs(BaseModel):
    slug: str = Field(description="Skill slug from the skills index")


class CallAgentArgs(BaseModel):
    agent_slug: str = Field(description="Allowed sub-agent slug")
    input: str = Field(description="Prompt for the sub-agent")


class MemoryWriteArgs(BaseModel):
    key: str = Field(description="Stable memory key")
    content: str = Field(description="Text to remember")
    tags: list[str] = Field(default_factory=list, description="Optional tags")


class MemorySearchArgs(BaseModel):
    query: str = Field(description="Substring to search")
    limit: int = Field(default=5, ge=1, le=20)


class MemoryDeleteArgs(BaseModel):
    key: str = Field(description="Memory key to delete")


def _build_skill_tool(skill_defs: list[dict[str, Any]]) -> StructuredTool:
    skills = {
        str(item.get("slug")): item
        for item in skill_defs
        if str(item.get("slug") or "").strip()
    }

    async def _load(slug: str) -> str:
        skill = skills.get(slug)
        if skill is None:
            return f"error: unknown skill {slug!r}"
        body = str(skill.get("content") or "").strip()
        if not body:
            return f"error: empty skill body {slug!r}"
        title = str(skill.get("name") or slug)
        text = f"## Skill: {title}\n\n{body}"
        limit = _skill_limit()
        if len(text) > limit:
            text = text[:limit] + "\n…(truncated)"
        return text

    return StructuredTool.from_function(
        coroutine=_load,
        name="load_skill",
        description=(
            "Load the full instructions for one skill listed in the skills index."
        ),
        args_schema=LoadSkillArgs,
    )


def _build_subrun_tool(sub_agents: list[str], hook: Any) -> StructuredTool:
    allowed = {str(item) for item in sub_agents}

    async def _call(agent_slug: str, input: str) -> str:
        if agent_slug not in allowed:
            return f"error: sub-agent {agent_slug!r} is not allowed"
        return await hook(agent_slug, input)

    return StructuredTool.from_function(
        coroutine=_call,
        name="call_agent",
        description="Run one allowed sub-agent and return its output.",
        args_schema=CallAgentArgs,
    )


def _build_memory_tools(hook: Any) -> list[BaseTool]:
    async def write(key: str, content: str, tags: list[str] | None = None) -> str:
        return await hook("write", {"key": key, "content": content, "tags": tags or []})

    async def search(query: str, limit: int = 5) -> str:
        return await hook("search", {"query": query, "limit": limit})

    async def remove(key: str) -> str:
        return await hook("delete", {"key": key})

    return [
        StructuredTool.from_function(
            coroutine=write,
            name="memory_write",
            description="Store a durable note for this agent and user.",
            args_schema=MemoryWriteArgs,
        ),
        StructuredTool.from_function(
            coroutine=search,
            name="memory_search",
            description="Search durable notes for this agent and user.",
            args_schema=MemorySearchArgs,
        ),
        StructuredTool.from_function(
            coroutine=remove,
            name="memory_delete",
            description="Delete one durable note by key.",
            args_schema=MemoryDeleteArgs,
        ),
    ]


def compose_prompt(system_prompt: str, skill_defs: list[dict[str, Any]] | None) -> str:
    """Keep only a skills index in the prompt; bodies load on demand."""
    base = system_prompt.strip()
    lines: list[str] = []
    for skill in skill_defs or []:
        slug = str(skill.get("slug") or "").strip()
        if not slug:
            continue
        description = str(skill.get("description") or "").strip().replace("\n", " ")
        if len(description) > 300:
            description = description[:300].rstrip() + "…"
        suffix = f" — {description}" if description else ""
        lines.append(
            f"- {slug}{suffix}. Call load_skill(\"{slug}\") for full instructions."
        )
    if not lines:
        return base
    return f"{base}\n\n{SKILL_HEADER}\n\n" + "\n".join(lines)


def context_hook(max_tokens: int):
    """Trim chat history before each model call without touching persisted state."""

    def compact(state: dict[str, Any]) -> dict[str, Any]:
        messages = state.get("messages") or []
        if not isinstance(messages, list) or not messages:
            return {}
        trimmed: list[BaseMessage] = trim_messages(
            messages,
            max_tokens=max_tokens,
            token_counter=count_tokens_approximately,
            strategy="last",
            allow_partial=False,
            start_on="human",
            include_system=True,
        )
        return {"llm_input_messages": trimmed}

    return compact


async def stream_agent(
    agent: AgentConfig,
    prompt: str,
    run_override: LLMConfig | None,
    max_steps: int,
) -> AsyncIterator[AgentEvent]:
    """Stream runtime events for one agent run. Timeouts are enforced by RunManager."""
    if agent.kind == "plugin":
        plugin = get_plugin(agent.plugin_name or "")
        async for event in plugin(prompt, run_override, max_steps):
            yield event
        return

    settings = get_settings()
    inputs = {"messages": [{"role": "user", "content": prompt}]}
    config: dict[str, Any] = {"recursion_limit": max(4, max_steps * 2 + 2)}
    if settings.langfuse_enabled:
        config["callbacks"] = [_langfuse_callback()]

    # MCP sessions live exactly as long as this run (closed on exit of the stack).
    async with AsyncExitStack() as stack:
        tools = _agent_tools(
            agent.tools,
            agent.tool_defs,
            approval_hook=agent.approval_hook,
            approval_mode=agent.approval_mode,
        )
        if agent.mcp_defs:
            mcp_tools = await build_mcp_tools(agent.mcp_defs, stack)
            if agent.approval_hook is not None and agent.approval_mode in {
                "all",
                "mutating",
            }:
                mcp_tools = [
                    ApprovalTool.wrap(tool, agent.approval_hook)
                    for tool in mcp_tools
                ]
            tools.extend(mcp_tools)
        if agent.skill_defs and not any(tool.name == "load_skill" for tool in tools):
            tools.append(_build_skill_tool(agent.skill_defs))
        if (
            agent.sub_agents
            and agent.subrun_hook is not None
            and not any(tool.name == "call_agent" for tool in tools)
        ):
            tools.append(
                _build_subrun_tool(agent.sub_agents, agent.subrun_hook)
            )
        if agent.memory_enabled and agent.memory_hook is not None:
            existing = {tool.name for tool in tools}
            tools.extend(
                tool
                for tool in _build_memory_tools(agent.memory_hook)
                if tool.name not in existing
            )
        graph = create_react_agent(
            build_llm(agent.llm, run_override),
            tools=tools,
            prompt=compose_prompt(agent.system_prompt, agent.skill_defs),
            pre_model_hook=(
                context_hook(settings.run_context_max_tokens)
                if settings.run_context_max_tokens > 0
                else None
            ),
        )
        async for event in graph.astream_events(inputs, version="v2", config=config):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                delta = _text(event["data"]["chunk"].content)
                if delta:
                    yield AgentEvent("message.delta", {"delta": delta})
            elif kind == "on_tool_start":
                yield AgentEvent(
                    "tool.call",
                    {"tool": event.get("name"), "input": event["data"].get("input")},
                )
            elif kind == "on_tool_end":
                yield AgentEvent(
                    "tool.result",
                    {
                        "tool": event.get("name"),
                        "output": _tool_output_text(event["data"].get("output")),
                    },
                )
            elif kind == "on_chat_model_end":
                yield AgentEvent("agent.step", {"node": event.get("name")})
                output = event["data"].get("output")
                usage = _usage_from_output(output)
                if usage is not None:
                    response_metadata = getattr(output, "response_metadata", None) or {}
                    yield AgentEvent(
                        "token.usage",
                        {
                            **usage,
                            "model": response_metadata.get("model_name"),
                        },
                    )
