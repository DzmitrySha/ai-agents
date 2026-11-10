"""`/v1/settings`: project-wide LLM endpoint, key and model list.

The saved row overrides env defaults (`DEFAULT_LLM_BASE_URL`/`_MODEL`/`_API_KEY`);
agents and the autofill helpers pick it up through `app.runtime.llm_config`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.deps import SessionDep, require_csrf, require_scope
from app.auth.principal import Principal
from app.repos import llm_providers as providers_repo
from app.repos import project_settings
from app.runtime.llm_config import ModelsError, fetch_models, refresh
from app.runtime.models import (
    ActiveProviderRequest,
    LLMModelsOut,
    LLMModelsRequest,
    LLMProviderCreate,
    LLMProviderDeleted,
    LLMProviderOut,
    LLMProvidersOut,
    LLMProviderUpdate,
    LLMSettingsOut,
    LLMSettingsUpdate,
)

router = APIRouter(
    prefix="/v1/settings", tags=["settings"], dependencies=[Depends(require_csrf)]
)


@router.get("/llm", response_model=LLMSettingsOut)
async def get_llm_settings(
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_scope("agents:read"))],
) -> LLMSettingsOut:
    config, source, row = await project_settings.resolve(session)
    return project_settings.to_out(config, source, row)


@router.put("/llm", response_model=LLMSettingsOut)
async def put_llm_settings(
    payload: LLMSettingsUpdate,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("admin"))],
) -> LLMSettingsOut:
    config, row = await project_settings.save(session, principal, payload)
    await refresh(session)
    return project_settings.to_out(config, "db", row)


async def _providers_state(session: SessionDep) -> LLMProvidersOut:
    config, source, row = await project_settings.resolve(session)
    return LLMProvidersOut(
        items=[providers_repo.to_out(p) for p in await providers_repo.list_providers(session)],
        active_id=await providers_repo.active_id(session),
        effective=project_settings.to_out(config, source, row),
    )


@router.get("/llm/providers", response_model=LLMProvidersOut)
async def list_providers(
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_scope("agents:read"))],
) -> LLMProvidersOut:
    return await _providers_state(session)


@router.post(
    "/llm/providers", response_model=LLMProviderOut, status_code=status.HTTP_201_CREATED
)
async def create_provider(
    payload: LLMProviderCreate,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require_scope("admin"))],
) -> LLMProviderOut:
    try:
        provider = await providers_repo.create_provider(session, principal, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await refresh(session)
    return providers_repo.to_out(provider)


@router.patch("/llm/providers/{provider_id}", response_model=LLMProviderOut)
async def update_provider(
    provider_id: str,
    payload: LLMProviderUpdate,
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_scope("admin"))],
) -> LLMProviderOut:
    provider = await providers_repo.get_provider(session, provider_id)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="provider not found"
        )
    try:
        updated = await providers_repo.update_provider(session, provider, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await refresh(session)
    return providers_repo.to_out(updated)


@router.delete("/llm/providers/{provider_id}", response_model=LLMProviderDeleted)
async def delete_provider(
    provider_id: str,
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_scope("admin"))],
) -> LLMProviderDeleted:
    provider = await providers_repo.get_provider(session, provider_id)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="provider not found"
        )
    await providers_repo.delete_provider(session, provider)
    await refresh(session)
    return LLMProviderDeleted(deleted=True, active_id=await providers_repo.active_id(session))


@router.put("/llm/active", response_model=LLMProvidersOut)
async def set_active_provider(
    payload: ActiveProviderRequest,
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_scope("admin"))],
) -> LLMProvidersOut:
    if payload.provider_id is not None:
        provider = await providers_repo.get_provider(session, payload.provider_id)
        if provider is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="provider not found"
            )
    await providers_repo.set_active(session, payload.provider_id)
    await refresh(session)
    return await _providers_state(session)


@router.post("/llm/models", response_model=LLMModelsOut)
async def list_llm_models(
    payload: LLMModelsRequest,
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_scope("agents:read"))],
) -> LLMModelsOut:
    config, _source, _row = await project_settings.resolve(session)
    base_url = (payload.base_url or config.base_url or "").strip()
    api_key = payload.api_key or config.api_key
    try:
        models = await fetch_models(
            base_url,
            api_key,
            auth_type=payload.auth_type or config.auth_type,
            auth_header=payload.auth_header or config.auth_header,
            auth_prefix=(
                payload.auth_prefix
                if payload.auth_prefix is not None
                else config.auth_prefix
            ),
        )
    except ModelsError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return LLMModelsOut(base_url=base_url, models=models)
