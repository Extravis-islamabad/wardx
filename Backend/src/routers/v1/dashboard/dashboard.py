"""Dashboard router.

GET /dashboard/summary     — headline counts, and the signed-in user's own
GET /dashboard/attention   — directory outage, break-glass coverage and safes needing
                             attention (audit.view or safes.manage)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.contracts.schemas.responses.common import UNAUTHORIZED_RESPONSE, APIResponse, ok
from src.contracts.schemas.responses.dashboard.dashboard_responses import (
    DashboardSummaryResponse,
)
from src.contracts.schemas.responses.safes.safe_responses import AttentionResponse
from src.core.permissions import AUDIT_VIEW, DASHBOARD_VIEW, SAFES_MANAGE
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.dashboard import DashboardServiceDep
from src.dependencies.safes import SafeHealthServiceDep
from src.routers.v1.safes.health_mappers import attention_response

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/summary",
    response_model=APIResponse[DashboardSummaryResponse],
    dependencies=[Depends(require_permission(DASHBOARD_VIEW))],
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


@router.get(
    "/attention",
    response_model=APIResponse[AttentionResponse],
    dependencies=[Depends(require_permission(AUDIT_VIEW, SAFES_MANAGE))],
    summary="What needs an administrator's attention: outage, break-glass, safe health",
    responses={**UNAUTHORIZED_RESPONSE},
)
async def attention(service: SafeHealthServiceDep) -> APIResponse[AttentionResponse]:
    return ok(attention_response(await service.attention()))
