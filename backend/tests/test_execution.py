"""Preset graph event translation and tool wiring (graph/LLM mocked)."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.execution import AgentConfig, stream_agent


def _config(**overrides) -> AgentConfig:
    base = dict(
        kind="preset",
        plugin_name=None,
        system_prompt="You are a test agent.",
        tools=["get_server_time"],
        llm={},
        limits={},
    )
    base.update(overrides)
    return AgentConfig(**base)


class _FakeGraph:
    async def astream_events(self, inputs, version="v2", config=None):
        assert inputs["messages"][0]["content"] == "hi"
        assert config["recursion_limit"] >= 4
        yield {
            "event": "on_chat_model_stream",
            "name": "model",
            "data": {"chunk": SimpleNamespace(content="Hel")},
        }
        yield {
            "event": "on_chat_model_stream",
            "name": "model",
            "data": {"chunk": SimpleNamespace(content=[{"type": "text", "text": "lo"}])},
        }
        yield {
            "event": "on_tool_start",
            "name": "get_server_time",
            "data": {"input": {}},
        }
        yield {
            "event": "on_tool_end",
            "name": "get_server_time",
            "data": {"output": SimpleNamespace(content="2026-11-03T00:00:00+00:00")},
        }
        yield {"event": "on_chat_model_end", "name": "model", "data": {}}


async def test_graph_events_are_translated(monkeypatch):
    from app.agents import execution

    monkeypatch.setattr(execution, "build_llm", lambda *a, **k: object())
    monkeypatch.setattr(execution, "create_react_agent", lambda *a, **k: _FakeGraph())

    events = [event async for event in stream_agent(_config(), "hi", None, max_steps=8)]

    assert [(event.type, event.data) for event in events] == [
        ("message.delta", {"delta": "Hel"}),
        ("message.delta", {"delta": "lo"}),
        ("tool.call", {"tool": "get_server_time", "input": {}}),
        (
            "tool.result",
            {"tool": "get_server_time", "output": "2026-11-03T00:00:00+00:00"},
        ),
        ("agent.step", {"node": "model"}),
    ]


async def test_prompt_and_tools_come_from_agent_config(monkeypatch):
    from app.agents import execution

    captured = {}

    def fake_create_react_agent(model, tools=None, prompt=None, **kwargs):
        captured["tools"] = [getattr(tool, "name", tool) for tool in tools or []]
        captured["prompt"] = prompt
        return _FakeGraph()

    monkeypatch.setattr(execution, "build_llm", lambda *a, **k: object())
    monkeypatch.setattr(execution, "create_react_agent", fake_create_react_agent)

    _ = [event async for event in stream_agent(_config(), "hi", None, max_steps=8)]

    assert captured["tools"] == ["get_server_time"]
    assert captured["prompt"] == "You are a test agent."


async def test_unknown_tool_raises():
    import pytest

    with pytest.raises(RuntimeError, match="unknown tool"):
        _ = [
            event
            async for event in stream_agent(
                _config(tools=["missing-tool"]), "hi", None, max_steps=8
            )
        ]


async def test_unknown_plugin_raises():
    import pytest

    with pytest.raises(RuntimeError, match="unknown plugin"):
        _ = [
            event
            async for event in stream_agent(
                _config(kind="plugin", plugin_name="missing"), "hi", None, max_steps=8
            )
        ]


async def test_skill_defs_are_appended_to_prompt(monkeypatch):
    from app.agents import execution

    captured = {}

    def fake_create_react_agent(model, tools=None, prompt=None, **kwargs):
        captured["prompt"] = prompt
        captured["tools"] = [getattr(tool, "name", tool) for tool in tools or []]
        return _FakeGraph()

    monkeypatch.setattr(execution, "build_llm", lambda *a, **k: object())
    monkeypatch.setattr(execution, "create_react_agent", fake_create_react_agent)

    config = _config(
        tools=["weather"],
        tool_defs=[
            {
                "slug": "weather",
                "name": "Weather",
                "description": "forecast",
                "method": "GET",
                "url": "https://api.test/{city}",
                "headers": {},
                "query": {},
                "body_template": None,
                "content_type": "application/json",
                "parameters": [{"name": "city", "type": "string", "required": True}],
                "timeout_seconds": 5,
            }
        ],
        skill_defs=[
            {
                "slug": "style",
                "name": "Style",
                "description": "Keep it short",
                "content": "Be terse.",
            }
        ],
    )
    _ = [event async for event in stream_agent(config, "hi", None, max_steps=8)]

    assert "Base prompt" not in captured["prompt"]
    assert "Be terse." not in captured["prompt"]
    assert 'load_skill("style")' in captured["prompt"]
    assert captured["prompt"].startswith("You are a test agent.")
    assert "# Skills (procedural knowledge)" in captured["prompt"]
    assert captured["tools"] == ["weather", "load_skill"]


def test_compose_prompt_without_skills_is_plain():
    from app.agents.execution import compose_prompt

    assert compose_prompt("  hello  ", []) == "hello"


async def test_load_skill_tool_returns_body(monkeypatch):
    from app.agents import execution

    tool = execution._build_skill_tool(
        [{"slug": "style", "name": "Style", "content": "Be terse."}]
    )
    assert (await tool.ainvoke({"slug": "style"})).endswith("Be terse.")
    assert (await tool.ainvoke({"slug": "missing"})).startswith("error: unknown skill")


def test_context_hook_keeps_system_and_recent():
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.agents.execution import context_hook

    messages = [
        SystemMessage(content="system"),
        *[
            HumanMessage(content=f"old {index} " + "x" * 200)
            for index in range(8)
        ],
    ]
    result = context_hook(120)({"messages": messages})
    trimmed = result["llm_input_messages"]
    assert trimmed[0].content == "system"
    assert len(trimmed) < len(messages)
