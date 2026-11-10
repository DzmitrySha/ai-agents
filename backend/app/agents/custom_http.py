"""No-code HTTP tools: schema builder, templating, LangChain bridge."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

import httpx
from langchain_core.tools import StructuredTool
from pydantic import Field, create_model

from app.agents.url_safety import UnsafeUrlError, assert_public_http_url
from app.settings import get_settings

PARAM_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_HTTP_METHODS_WITH_BODY = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_TYPE_HINTS: dict[str, Any] = {
    "string": str,
    "number": float,
    "integer": int,
    "boolean": bool,
}


def json_schema(parameters: list[dict[str, Any]]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param in parameters:
        name = str(param["name"])
        entry: dict[str, Any] = {
            "title": name,
            "type": "boolean"
            if param.get("type") == "boolean"
            else str(param.get("type") or "string"),
        }
        if param.get("description"):
            entry["description"] = param["description"]
        if param.get("enum"):
            entry["enum"] = list(param["enum"])
        properties[name] = entry
        if param.get("required", True):
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}


def _args_model(name: str, parameters: list[dict[str, Any]]):
    fields: dict[str, Any] = {}
    for param in parameters:
        python_type = _TYPE_HINTS.get(str(param.get("type") or "string"), str)
        required = param.get("required", True)
        fields[str(param["name"])] = (
            python_type if required else python_type | None,
            Field(
                ... if required else None,
                description=str(param.get("description") or ""),
            ),
        )
    return create_model(f"{name.title().replace('-', '')}Args", **fields)


def _coerce(param: dict[str, Any], value: Any) -> Any:
    if value is None:
        return None
    kind = str(param.get("type") or "string")
    try:
        if kind == "integer":
            return int(value)
        if kind == "number":
            return float(value)
        if kind == "boolean":
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in {"1", "true", "yes", "on"}
    except (TypeError, ValueError) as exc:
        raise ValueError(f"parameter {param['name']!r} expects {kind}") from exc
    return str(value)


def _render(
    template: str,
    params: dict[str, Any],
    *,
    mode: str,
    param_types: dict[str, str] | None = None,
) -> str:
    types = param_types or {}

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        value = params.get(name, "")
        if mode == "url":
            return quote(str(value), safe="")
        if mode == "json":
            # Строковые параметры подставляются внутрь кавычек JSON-строки,
            # числовые/булевы — как сырое JSON-значение (без кавычек в шаблоне).
            if types.get(name, "string") == "string":
                return json.dumps(str(value), ensure_ascii=False)[1:-1]
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    return PARAM_PLACEHOLDER.sub(_replace, template)


def _validate(parameters: list[dict[str, Any]], values: dict[str, Any]) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for param in parameters:
        name = str(param["name"])
        raw = values.get(name)
        if raw is None or raw == "":
            if param.get("required", True):
                raise ValueError(f"missing parameter {name!r}")
            continue
        value = _coerce(param, raw)
        allowed = param.get("enum")
        if allowed and str(value) not in [str(item) for item in allowed]:
            raise ValueError(f"parameter {name!r} must be one of {allowed}")
        resolved[name] = value
    unknown = set(values) - {str(param["name"]) for param in parameters}
    if unknown:
        raise ValueError(f"unknown parameters: {', '.join(sorted(unknown))}")
    return resolved


def definition_from_row(row: Any) -> dict[str, Any]:
    """Freeze a custom tool config into an agent version snapshot."""
    return {
        "slug": row.slug,
        "name": row.name,
        "description": row.description or "",
        "method": row.method,
        "url": row.url,
        "headers": dict(row.headers or {}),
        "query": dict(row.query or {}),
        "body_template": row.body_template,
        "content_type": row.content_type or "application/json",
        "parameters": list(row.parameters or []),
        "timeout_seconds": int(row.timeout_seconds or 20),
    }


async def invoke(definition: dict[str, Any], values: dict[str, Any]) -> str:
    """Execute the templated HTTP call; returns text (errors are text, not exceptions)."""
    try:
        params = _validate(list(definition.get("parameters") or []), values)
    except ValueError as exc:
        return f"error: {exc}"

    method = str(definition.get("method") or "GET").upper()
    param_types = {
        str(param["name"]): str(param.get("type") or "string")
        for param in definition.get("parameters") or []
    }
    url = _render(str(definition.get("url") or ""), params, mode="url")
    try:
        assert_public_http_url(url)
    except UnsafeUrlError as exc:
        return f"error: {exc}"
    headers = {
        str(key): _render(str(value), params, mode="raw")
        for key, value in (definition.get("headers") or {}).items()
    }
    # Query values are encoded by httpx; pre-quoting would double-encode.
    query = {
        str(key): _render(str(value), params, mode="raw")
        for key, value in (definition.get("query") or {}).items()
    }
    body_text: str | None = None
    template = definition.get("body_template")
    if template and (method in _HTTP_METHODS_WITH_BODY or template.strip()):
        body_text = _render(str(template), params, mode="json", param_types=param_types)
        headers.setdefault("Content-Type", str(definition.get("content_type") or "application/json"))

    timeout = float(definition.get("timeout_seconds") or 20)
    try:
        # No automatic redirects: Location could point at private IPs (SSRF).
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.request(
                method,
                url,
                params=query or None,
                headers=headers or None,
                content=body_text,
            )
    except Exception as exc:  # noqa: BLE001 - report as tool output
        return f"error: {type(exc).__name__}: {exc}"

    text = response.text or ""
    limit = get_settings().run_tool_output_max_chars
    if len(text) > limit:
        text = text[:limit] + "\n…(truncated)"
    if response.status_code >= 400:
        return f"error: HTTP {response.status_code}: {text[:1000]}"
    return text


def build_tool(definition: dict[str, Any]) -> StructuredTool:
    slug = str(definition["slug"])
    parameters = list(definition.get("parameters") or [])

    async def _run(**kwargs: Any) -> str:
        return await invoke(definition, kwargs)

    return StructuredTool.from_function(
        coroutine=_run,
        name=slug,
        description=str(definition.get("description") or definition.get("name") or slug),
        args_schema=_args_model(slug, parameters),
    )
