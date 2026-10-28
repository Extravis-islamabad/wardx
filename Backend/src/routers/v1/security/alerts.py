"""Security alerts router. Alerts are never deleted.

GET  /alerts                        — page through alerts (audit.view)
POST /alerts/{alert_id}/acknowledge — acknowledge an alert (alerts.acknowledge; audited)
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends

from src.contracts.dto.security.alert_dto import AlertDTO, AlertFilterDTO
from src.contracts.schemas.requests.common import PageParams
from src.contracts.schemas.responses.common import (
    CONFLICT_RESPONSE,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    APIResponse,
    PaginatedAPIResponse,
    ok,
)
from src.contracts.schemas.responses.security.alert_responses import AlertResponse
from src.core.permissions import ALERTS_ACKNOWLEDGE, AUDIT_VIEW
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.identity import AlertServiceDep

router = APIRouter(prefix="/alerts", tags=["security"])


def _to_response(dto: AlertDTO) -> AlertResponse:
    return AlertResponse(
        id=dto.id,
        created_at=dto.created_at,
        severity=dto.severity,
        kind=dto.kind,
        message=dto.message,
        actor_id=dto.actor_id,
        actor_name=dto.actor_name,
        object_type=dto.object_type,
        object_id=dto.object_id,
        details=dto.details,
        acknowledged_by=dto.acknowledged_by,
        acknowledged_at=dto.acknowledged_at,
    )


@router.get(
    "",
    response_model=PaginatedAPIResponse[AlertResponse],
    dependencies=[Depends(require_permission(AUDIT_VIEW))],
    summary="List security alerts",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def list_alerts(
    service: AlertServiceDep,
    paging: Annotated[PageParams, Depends()],
    severity: Literal["low", "medium", "high"] | None = None,
    acknowledged: bool | None = None,
) -> PaginatedAPIResponse[AlertResponse]:
    rows, total = await service.list(
        AlertFilterDTO(severity=severity, acknowledged=acknowledged),
        page=paging.page,
        page_size=paging.page_size,
    )
    return PaginatedAPIResponse[AlertResponse](
        data=[_to_response(a) for a in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.post(
    "/{alert_id}/acknowledge",
    response_model=APIResponse[AlertResponse],
    dependencies=[Depends(require_permission(ALERTS_ACKNOWLEDGE))],
    summary="Acknowledge a security alert",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
    },
)
async def acknowledge(
    alert_id: uuid.UUID, service: AlertServiceDep, actor: ActorDep
) -> APIResponse[AlertResponse]:
    return ok(_to_response(await service.acknowledge(actor, alert_id)), "Alert acknowledged")
