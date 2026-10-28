"""Access requests router — asking for, approving and cancelling access.

GET  /requests                         — page through requests (approvers see all)
POST /requests                         — ask to use an account that needs approval
POST /requests/{request_id}/decision   — approve or deny (never your own)
POST /requests/{request_id}/cancel     — the requester withdraws an open request
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.contracts.dto.access.access_request_dto import AccessRequestDTO
from src.contracts.schemas.requests.access.access_request_requests import (
    RequestCreate,
    RequestDecision,
)
from src.contracts.schemas.requests.common import PageParams
from src.contracts.schemas.responses.access.access_request_responses import (
    AccessRequestResponse,
)
from src.contracts.schemas.responses.common import (
    CONFLICT_RESPONSE,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
    APIResponse,
    PaginatedAPIResponse,
    ok,
)
from src.core.enums import RequestStatus
from src.core.permissions import ACCESS_APPROVE, ACCESS_USE
from src.dependencies.access import AccessRequestServiceDep
from src.dependencies.auth import ActorDep, require_permission
from src.routers.v1.access.briefs import account_brief_response, user_brief_response

router = APIRouter(prefix="/requests", tags=["access"])


def _to_response(dto: AccessRequestDTO) -> AccessRequestResponse:
    return AccessRequestResponse(
        id=dto.id,
        account=account_brief_response(dto.account),
        requester=user_brief_response(dto.requester),
        reason=dto.reason,
        ticket_ref=dto.ticket_ref,
        duration_minutes=dto.duration_minutes,
        status=RequestStatus(dto.status),
        decided_by=user_brief_response(dto.decided_by) if dto.decided_by else None,
        decided_at=dto.decided_at,
        decision_note=dto.decision_note,
        expires_at=dto.expires_at,
        created_at=dto.created_at,
    )


@router.get(
    "",
    response_model=PaginatedAPIResponse[AccessRequestResponse],
    dependencies=[Depends(require_permission(ACCESS_USE))],
    summary="List access requests",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def list_requests(
    service: AccessRequestServiceDep,
    actor: ActorDep,
    paging: Annotated[PageParams, Depends()],
    status: RequestStatus | None = None,
    mine: bool = False,
) -> PaginatedAPIResponse[AccessRequestResponse]:
    rows, total = await service.list(
        actor, page=paging.page, page_size=paging.page_size, status=status, mine=mine
    )
    return PaginatedAPIResponse[AccessRequestResponse](
        data=[_to_response(r) for r in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.post(
    "",
    response_model=APIResponse[AccessRequestResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(ACCESS_USE))],
    summary="Request access to an account that needs approval",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def create_request(
    request: RequestCreate, service: AccessRequestServiceDep, actor: ActorDep
) -> APIResponse[AccessRequestResponse]:
    created = await service.create(
        actor,
        account_id=request.account_id,
        reason=request.reason,
        ticket_ref=request.ticket_ref,
        duration_minutes=request.duration_minutes,
    )
    return ok(_to_response(created))


@router.post(
    "/{request_id}/decision",
    response_model=APIResponse[AccessRequestResponse],
    dependencies=[Depends(require_permission(ACCESS_APPROVE))],
    summary="Approve or deny an access request",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def decide_request(
    request_id: uuid.UUID,
    request: RequestDecision,
    service: AccessRequestServiceDep,
    actor: ActorDep,
) -> APIResponse[AccessRequestResponse]:
    decided = await service.decide(actor, request_id, approve=request.approve, note=request.note)
    return ok(_to_response(decided))


@router.post(
    "/{request_id}/cancel",
    response_model=APIResponse[AccessRequestResponse],
    dependencies=[Depends(require_permission(ACCESS_USE))],
    summary="Cancel your open access request",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
    },
)
async def cancel_request(
    request_id: uuid.UUID, service: AccessRequestServiceDep, actor: ActorDep
) -> APIResponse[AccessRequestResponse]:
    return ok(_to_response(await service.cancel(actor, request_id)))
