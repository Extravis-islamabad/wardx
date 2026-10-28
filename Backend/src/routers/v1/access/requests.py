"""Access requests router — asking for, approving and cancelling access.

GET  /requests                         — page through requests: yours (mine), the ones you
                                         can decide now (queue), or those in safes you can list
POST /requests                         — ask to use an account whose safe requires approval
POST /requests/{request_id}/decision   — approve or deny at the current level (eligibility
                                         is checked per safe and level, never your own)
POST /requests/{request_id}/cancel     — the requester withdraws an open request
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

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
from src.core.permissions import ACCESS_USE
from src.dependencies.access import AccessRequestServiceDep
from src.dependencies.auth import ActorDep, require_permission
from src.routers.v1.access.request_mappers import request_response

router = APIRouter(prefix="/requests", tags=["access"])


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
    queue: bool = False,
) -> PaginatedAPIResponse[AccessRequestResponse]:
    rows, total = await service.list(
        actor,
        page=paging.page,
        page_size=paging.page_size,
        status=status,
        mine=mine,
        queue=queue,
    )
    return PaginatedAPIResponse[AccessRequestResponse](
        data=[request_response(r) for r in rows],
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
    return ok(request_response(created))


@router.post(
    "/{request_id}/decision",
    response_model=APIResponse[AccessRequestResponse],
    # Who may decide is the safe's policy ('approve' + the level's approvers), checked in
    # the service; the route only needs a signed-in console user.
    dependencies=[Depends(require_permission(ACCESS_USE))],
    summary="Approve or deny an access request at its current level",
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
    return ok(request_response(decided))


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
    return ok(request_response(await service.cancel(actor, request_id)))
