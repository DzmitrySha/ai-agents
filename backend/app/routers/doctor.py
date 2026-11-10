"""Read-only platform doctor endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.auth.deps import require_scope
from app.auth.principal import Principal
from app.runtime.doctor import run_doctor
from app.runtime.models import DoctorResult

router = APIRouter(prefix="/v1/doctor", tags=["doctor"])


@router.get("", response_model=DoctorResult)
async def doctor(
    request: Request,
    _principal: Annotated[Principal, Depends(require_scope("admin"))],
) -> DoctorResult:
    return await run_doctor(
        request.app.state.session_factory,
        request.app.state.settings,
        request.app.state.run_manager,
    )
