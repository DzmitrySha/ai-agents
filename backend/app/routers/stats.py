"""`/v1/stats`: usage analytics for runs, tools and API (chart-ready aggregates)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.auth.deps import SessionDep, require_csrf, require_scope
from app.auth.principal import Principal
from app.repos import usage as usage_repo
from app.runtime.models import StatsOverview

router = APIRouter(
    prefix="/v1/stats", tags=["stats"], dependencies=[Depends(require_csrf)]
)


@router.get("/overview", response_model=StatsOverview)
async def stats_overview(
    session: SessionDep,
    _principal: Annotated[Principal, Depends(require_scope("runs:read"))],
    days: int = Query(default=14, ge=1, le=90),
) -> StatsOverview:
    return await usage_repo.overview(session, days)
