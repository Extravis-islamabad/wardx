"""Audit trail router.

GET  /audit/events   — page through events, newest first, with filters
POST /audit/verify   — walk the hash chain and report the first broken link
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.contracts.dto.audit.audit_event_dto import AuditEventDTO, AuditFilterDTO
from src.contracts.schemas.requests.common import PageParams
from src.contracts.schemas.responses.audit.audit_responses import (
    AuditEventResponse,
    ChainVerificationResponse,
)
from src.contracts.schemas.responses.common import (
    FORBIDDEN_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    APIResponse,
    PaginatedAPIResponse,
    ok,
)
from src.core.permissions import AUDIT_VIEW
from src.dependencies.audit import AuditServiceDep
from src.dependencies.auth import require_permission

router = APIRouter(prefix="/audit", tags=["audit"])


def _to_response(dto: AuditEventDTO) -> AuditEventResponse:
    return AuditEventResponse(
        seq=dto.seq,
        id=dto.id,
        occurred_at=dto.occurred_at,
        actor_id=dto.actor_id,
        actor_name=dto.actor_name,
        action=dto.action,
        object_type=dto.object_type,
        object_id=dto.object_id,
        outcome=dto.outcome,
        source_ip=dto.source_ip,
        details=dto.details,
        hash=dto.hash,
    )


@router.get(
    "/events",
    response_model=PaginatedAPIResponse[AuditEventResponse],
    dependencies=[Depends(require_permission(AUDIT_VIEW))],
    summary="List audit events",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def list_events(
    service: AuditServiceDep,
    paging: Annotated[PageParams, Depends()],
    action: Annotated[str | None, Query(max_length=80)] = None,
    actor_id: uuid.UUID | None = None,
    object_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> PaginatedAPIResponse[AuditEventResponse]:
    rows, total = await service.list_events(
        AuditFilterDTO(
            action=action, actor_id=actor_id, object_id=object_id, since=since, until=until
        ),
        page=paging.page,
        page_size=paging.page_size,
    )
    return PaginatedAPIResponse[AuditEventResponse](
        data=[_to_response(e) for e in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.post(
    "/verify",
    response_model=APIResponse[ChainVerificationResponse],
    dependencies=[Depends(require_permission(AUDIT_VIEW))],
    summary="Verify the audit hash chain",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def verify_chain(service: AuditServiceDep) -> APIResponse[ChainVerificationResponse]:
    result = await service.verify_chain()
    return ok(
        ChainVerificationResponse(
            ok=result.ok,
            checked=result.checked,
            broken_at_seq=result.broken_at_seq,
            reason=result.reason,
        )
    )
