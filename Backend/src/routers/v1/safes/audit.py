"""Safe-scoped audit router.

GET /safes/{safe_id}/audit — events about the safe, its accounts, and their requests and
check-outs ('view_audit' on the safe, or the global audit.view)
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.contracts.dto.audit.audit_event_dto import AuditFilterDTO
from src.contracts.schemas.requests.common import PageParams
from src.contracts.schemas.responses.audit.audit_responses import AuditEventResponse
from src.contracts.schemas.responses.common import (
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    PaginatedAPIResponse,
)
from src.core.permissions import INVENTORY_VIEW
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.safes import SafeAuditServiceDep
from src.routers.v1.audit.audit_events import audit_event_response

router = APIRouter(prefix="/safes/{safe_id}/audit", tags=["safes"])


@router.get(
    "",
    response_model=PaginatedAPIResponse[AuditEventResponse],
    dependencies=[Depends(require_permission(INVENTORY_VIEW))],
    summary="Audit events for a safe and its accounts",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def safe_audit(
    safe_id: uuid.UUID,
    service: SafeAuditServiceDep,
    actor: ActorDep,
    paging: Annotated[PageParams, Depends()],
    action: Annotated[str | None, Query(max_length=80)] = None,
) -> PaginatedAPIResponse[AuditEventResponse]:
    rows, total = await service.list(
        actor, safe_id, AuditFilterDTO(action=action), page=paging.page, page_size=paging.page_size
    )
    return PaginatedAPIResponse[AuditEventResponse](
        data=[audit_event_response(e) for e in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )
