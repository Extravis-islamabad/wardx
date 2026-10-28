from __future__ import annotations

from fastapi import APIRouter

from src.contracts.schemas.access import DashboardSummary
from src.contracts.schemas.common import APIResponse, ok
from src.dependencies.auth import ActorDep, SessionDep
from src.services import dashboard_service

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/summary", response_model=APIResponse[DashboardSummary])
async def summary(actor: ActorDep, session: SessionDep):
    return ok(await dashboard_service.summary(session, actor))
