"""Project-wide runtime settings persisted in `app_settings` (single row)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import Principal
from app.models import AppSetting, LLMProvider
from app.runtime.models import LLMConfig, LLMSettingsOut, LLMSettingsUpdate
from app.settings import get_settings

SETTINGS_ID = "default"
_NOT_A_KEY = frozenset({"", "not-needed", "none"})


def env_config() -> LLMConfig:
    settings = get_settings()
    return LLMConfig(
        base_url=settings.default_llm_base_url,
        model=settings.default_llm_model,
        api_key=settings.default_llm_api_key,
        auth_type="bearer",
        auth_header="Authorization",
        auth_prefix="Bearer ",
    )


async def get_row(session: AsyncSession) -> AppSetting | None:
    return await session.get(AppSetting, SETTINGS_ID)


async def resolve(
    session: AsyncSession,
) -> tuple[LLMConfig, str, AppSetting | None]:
    """Effective config: DB values override env field-by-field; source is 'env' if none set."""
    env = env_config()
    row = await get_row(session)
    if row is not None and row.active_llm_provider_id:
        provider = await session.get(LLMProvider, row.active_llm_provider_id)
        if provider is not None:
            # Провайдер перекрывает env по каждому полю: незаполненный ключ
            # берётся из DEFAULT_LLM_API_KEY (локальные LM Studio любят это).
            return (
                LLMConfig(
                    base_url=provider.base_url or env.base_url,
                    model=provider.model or env.model,
                    api_key=provider.api_key or env.api_key,
                    auth_type=provider.auth_type or "bearer",
                    auth_header=provider.auth_header or "Authorization",
                    auth_prefix=(
                        provider.auth_prefix
                        if provider.auth_prefix is not None
                        else "Bearer "
                    ),
                ),
                "provider",
                row,
            )
    if row is None:
        return env, "env", None
    if not any((row.llm_base_url, row.llm_model, row.llm_api_key)):
        return env, "env", row
    config = LLMConfig(
        base_url=row.llm_base_url or env.base_url,
        model=row.llm_model or env.model,
        api_key=row.llm_api_key or env.api_key,
        auth_type="bearer",
        auth_header="Authorization",
        auth_prefix="Bearer ",
    )
    return config, "db", row


def mask_key(api_key: str | None) -> tuple[bool, str | None]:
    """(is_set, hint) without leaking the secret."""
    value = (api_key or "").strip()
    if value.lower() in _NOT_A_KEY:
        return False, None
    hint = f"…{value[-4:]}" if len(value) > 4 else "…"
    return True, hint


def to_out(config: LLMConfig, source: str, row: AppSetting | None) -> LLMSettingsOut:
    is_set, hint = mask_key(config.api_key)
    return LLMSettingsOut(
        base_url=str(config.base_url or ""),
        model=str(config.model or ""),
        api_key_set=is_set,
        api_key_hint=hint,
        source=source if source in {"db", "env", "provider"} else "env",  # type: ignore[arg-type]
        auth_type=config.auth_type or "bearer",  # type: ignore[arg-type]
        auth_header=config.auth_header or "Authorization",
        auth_prefix=config.auth_prefix or "",
        updated_by=(row.updated_by or None) if row is not None else None,
        updated_at=getattr(row, "updated_at", None) if row is not None else None,
    )


async def save(
    session: AsyncSession, principal: Principal, data: LLMSettingsUpdate
) -> tuple[LLMConfig, AppSetting]:
    row = await get_row(session)
    if row is None:
        row = AppSetting(id=SETTINGS_ID, updated_by="")
        session.add(row)
    if data.base_url is not None:
        row.llm_base_url = data.base_url or None
    if data.model is not None:
        row.llm_model = data.model or None
    if data.clear_api_key:
        row.llm_api_key = None
    elif data.api_key:
        row.llm_api_key = data.api_key.strip() or None
    row.updated_by = principal.email or f"{principal.kind}:{principal.id}"
    await session.commit()
    await session.refresh(row)
    config, _source, _row = await resolve(session)
    return config, row
