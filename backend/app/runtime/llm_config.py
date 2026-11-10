"""Cached project LLM config + provider model listing.

`project_llm()` is what agent runs and the autofill helpers use: it prefers the
project row saved in `app_settings`, falling back to env defaults. Run code has
no DB session, so the value is cached and refreshed at startup and on every PUT.
"""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_setup import logger
from app.repos import project_settings
from app.runtime.models import LLMConfig

MODELS_TIMEOUT_SECONDS = 10.0
_PLACEHOLDER_KEYS = frozenset({"", "not-needed", "none"})

_cached: LLMConfig | None = None


class ModelsError(RuntimeError):
    """The provider did not answer with a usable model list."""


def project_llm() -> LLMConfig:
    return _cached or project_settings.env_config()


def set_cached(config: LLMConfig) -> None:
    global _cached
    _cached = config


async def refresh(session: AsyncSession) -> LLMConfig:
    """Reload from the DB; a missing table/DB never blocks startup."""
    try:
        config, _source, _row = await project_settings.resolve(session)
    except Exception as exc:  # noqa: BLE001 - fall back to env defaults
        logger.warning("LLM settings unavailable, using env: {}", exc)
        _cached = None
        return project_settings.env_config()
    set_cached(config)
    return config


def auth_headers(
    api_key: str | None,
    auth_type: str | None = "bearer",
    auth_header: str | None = "Authorization",
    auth_prefix: str | None = "Bearer ",
) -> dict[str, str]:
    """Token → HTTP header, exactly as the provider expects it.

    `bearer` — `<auth_header>: <auth_prefix><key>` (prefix defaults to "Bearer "),
    `header` — same with whatever prefix is configured (may be empty),
    `none` — no auth header at all.
    """
    value = (api_key or "").strip()
    if (auth_type or "bearer") == "none" or value.lower() in _PLACEHOLDER_KEYS:
        return {}
    name = (auth_header or "Authorization").strip() or "Authorization"
    return {name: f"{auth_prefix or ''}{value}"}


async def fetch_models(
    base_url: str,
    api_key: str | None,
    *,
    auth_type: str | None = None,
    auth_header: str | None = None,
    auth_prefix: str | None = None,
) -> list[str]:
    base = (base_url or "").strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise ModelsError("укажите base_url вида http://host:port/v1")
    url = f"{base}/models"
    project = project_llm()
    headers = auth_headers(
        api_key,
        auth_type or project.auth_type,
        auth_header or project.auth_header,
        auth_prefix if auth_prefix is not None else project.auth_prefix,
    )
    try:
        async with httpx.AsyncClient(timeout=MODELS_TIMEOUT_SECONDS) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise ModelsError(f"{type(exc).__name__}: {exc}") from exc
    if response.status_code >= 400:
        detail = response.text.strip()[:200]
        raise ModelsError(f"HTTP {response.status_code} от {url}: {detail}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ModelsError(f"ответ {url} не JSON") from exc
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ModelsError(f"ответ {url} не содержит поля data[]")
    models: list[str] = []
    for item in items:
        if isinstance(item, dict):
            model_id = item.get("id")
            if isinstance(model_id, str) and model_id and model_id not in models:
                models.append(model_id)
    if not models:
        raise ModelsError("провайдер не вернул ни одной модели")
    return models
