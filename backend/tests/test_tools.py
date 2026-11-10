"""Tool registry: `/v1/tools` plus calculator/now behavior."""

from __future__ import annotations

from tests.conftest import AUTH


def test_tools_endpoint_lists_registry(client):
    tools = client.get("/v1/tools", headers=AUTH).json()
    names = {tool["name"] for tool in tools}
    assert {"calculator", "now", "get_server_time"} <= names
    calculator = next(tool for tool in tools if tool["name"] == "calculator")
    assert calculator["description"]
    assert "expression" in calculator["parameters"]["properties"]


def test_calculator_evaluates_allowlisted_expression():
    from app.agents.tools import calculator

    assert calculator.invoke({"expression": "17*4+9"}) == "77"
    assert calculator.invoke({"expression": "(2+3)%2"}).startswith("1")
    assert calculator.invoke({"expression": "__import__('os')"}).startswith("error:")


def test_now_returns_time_and_rejects_unknown_zone():
    from app.agents.tools import now

    value = now.invoke({"timezone_name": "Europe/Minsk"})
    assert value and not value.startswith("error:")
    assert "error:" in now.invoke({"timezone_name": "Mars/Olympus"})


def test_get_server_time_returns_iso():
    from app.agents.tools import get_server_time

    value = get_server_time.invoke({})
    assert "T" in value
