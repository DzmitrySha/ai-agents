"""Named OpenAI-compatible LLM providers (LM Studio, vLLM, external APIs)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import Principal
from app.models import AppSetting, LLMProvider, utcnow
from app.repos import project_settings
from app.runtime.models import LLMProviderCreate, LLMProviderOut, LLMProviderUpdate

SETTINGS_ID = "default"


def to_out(provider: LLMProvider) -> LLMProviderOut:
    is_set, hint = project_settings.mask_key(provider.api_key)
    return LLMProviderOut(
        id=provider.id,
        name=provider.name,
        base_url=provider.base_url,
        model=provider.model,
        api_key_set=is_set,
        api_key_hint=hint,
        auth_type=provider.auth_type or "bearer",
        auth_header=provider.auth_header or "Authorization",
        auth_prefix=(
            provider.auth_prefix if provider.auth_prefix is not None else "Bearer "
        ),
        created_by=provider.created_by or None,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


async def list_providers(session: AsyncSession) -> list[LLMProvider]:
    stmt = select(LLMProvider).order_by(LLMProvider.name)
    return list((await session.execute(stmt)).scalars())


async def get_provider(session: AsyncSession, provider_id: str) -> LLMProvider | None:
    return await session.get(LLMProvider, provider_id)


async def _name_taken(
    session: AsyncSession, name: str, *, exclude_id: str | None = None
) -> bool:
    stmt = select(LLMProvider.id).where(LLMProvider.name == name)
    if exclude_id:
        stmt = stmt.where(LLMProvider.id != exclude_id)
    return (await session.execute(stmt)).first() is not None


async def create_provider(
    session: AsyncSession, principal: Principal, data: LLMProviderCreate
) -> LLMProvider:
    name = data.name.strip()
    if await _name_taken(session, name):
        raise ValueError("провайдер с таким именем уже есть")
    provider = LLMProvider(
        name=name,
        base_url=data.base_url,
        model=data.model.strip(),
        api_key=(data.api_key or "").strip() or None,
        auth_type=data.auth_type,
        auth_header=data.auth_header,
        auth_prefix=data.auth_prefix,
        created_by=principal.email or f"{principal.kind}:{principal.id}",
    )
    session.add(provider)
    await session.commit()
    await session.refresh(provider)
    return provider


async def update_provider(
    session: AsyncSession, provider: LLMProvider, data: LLMProviderUpdate
) -> LLMProvider:
    if data.name is not None:
        name = data.name.strip()
        if await _name_taken(session, name, exclude_id=provider.id):
            raise ValueError("провайдер с таким именем уже есть")
        provider.name = name
    if data.base_url is not None:
        provider.base_url = data.base_url
    if data.model is not None:
        provider.model = data.model.strip()
    if data.auth_type is not None:
        provider.auth_type = data.auth_type
    if data.auth_header is not None:
        provider.auth_header = data.auth_header
    if data.auth_prefix is not None:
        provider.auth_prefix = data.auth_prefix
    if data.clear_api_key:
        provider.api_key = None
    elif data.api_key:
        provider.api_key = data.api_key.strip() or None
    provider.updated_at = utcnow()
    await session.commit()
    await session.refresh(provider)
    return provider


async def delete_provider(session: AsyncSession, provider: LLMProvider) -> None:
    """Удаляет провайдера; если он был активным — активный указатель снимается."""
    row = await project_settings.get_row(session)
    if row is not None and row.active_llm_provider_id == provider.id:
        row.active_llm_provider_id = None
        row.updated_at = utcnow()
    await session.delete(provider)
    await session.commit()


async def active_id(session: AsyncSession) -> str | None:
    row = await project_settings.get_row(session)
    return row.active_llm_provider_id if row is not None else None


async def set_active(session: AsyncSession, provider_id: str | None) -> None:
    row = await project_settings.get_row(session)
    if row is None:
        row = AppSetting(id=SETTINGS_ID, updated_by="")
        session.add(row)
    row.active_llm_provider_id = provider_id
    row.updated_at = utcnow()
    await session.commit()
