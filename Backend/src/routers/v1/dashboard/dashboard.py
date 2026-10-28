"""Dashboard router.

GET /dashboard/summary   — headline counts, and the signed-in user's own
"""

from __future__ import annotations

from fastapi import APIRouter

from src.contracts.schemas.responses.common import UNAUTHORIZED_RESPONSE, APIResponse, ok
from src.contracts.schemas.responses.dashboard.dashboard_responses import (
    DashboardSummaryResponse,
)
from src.dependencies.auth import ActorDep
from src.dependencies.dashboard import DashboardServiceDep

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/summary",
    response_model=APIResponse[DashboardSummaryResponse],
    summary="Headline counts for the home page",
    responses={**UNAUTHORIZED_RESPONSE},
)
async def summary(
    service: DashboardServiceDep, actor: ActorDep
) -> APIResponse[DashboardSummaryResponse]:
    s = await service.summary(actor)
    return ok(
        DashboardSummaryResponse(
            targets=s.targets,
            accounts=s.accounts,
            accounts_without_secret=s.accounts_without_secret,
            active_checkouts=s.active_checkouts,
            pending_requests=s.pending_requests,
            my_active_checkouts=s.my_active_checkouts,
            my_open_requests=s.my_open_requests,
        )
    )
