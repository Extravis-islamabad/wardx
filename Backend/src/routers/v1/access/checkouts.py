"""Check-outs router — time-boxed use of a privileged credential.

GET  /checkouts                          — page through check-outs (auditors see all)
POST /checkouts                          — check an account out (directly or via a request)
POST /checkouts/{checkout_id}/reveal     — the holder reads the secret (audited, no-store)
POST /checkouts/{checkout_id}/checkin    — the holder returns it, or an admin revokes it
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from src.contracts.dto.access.checkout_dto import CheckoutDTO
from src.contracts.schemas.requests.access.checkout_requests import CheckoutCreate
from src.contracts.schemas.requests.common import PageParams
from src.contracts.schemas.responses.access.checkout_responses import (
    CheckoutResponse,
    RevealedSecretResponse,
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
from src.core.enums import CheckoutStatus
from src.core.permissions import ACCESS_USE
from src.dependencies.access import CheckoutServiceDep
from src.dependencies.auth import ActorDep, require_permission
from src.routers.v1.access.briefs import account_brief_response, user_brief_response

router = APIRouter(prefix="/checkouts", tags=["access"])


def _to_response(dto: CheckoutDTO) -> CheckoutResponse:
    return CheckoutResponse(
        id=dto.id,
        account=account_brief_response(dto.account),
        user=user_brief_response(dto.user),
        request_id=dto.request_id,
        reason=dto.reason,
        status=CheckoutStatus(dto.status),
        checked_out_at=dto.checked_out_at,
        expires_at=dto.expires_at,
        checked_in_at=dto.checked_in_at,
    )


@router.get(
    "",
    response_model=PaginatedAPIResponse[CheckoutResponse],
    dependencies=[Depends(require_permission(ACCESS_USE))],
    summary="List check-outs",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def list_checkouts(
    service: CheckoutServiceDep,
    actor: ActorDep,
    paging: Annotated[PageParams, Depends()],
    status: CheckoutStatus | None = None,
    mine: bool = False,
) -> PaginatedAPIResponse[CheckoutResponse]:
    rows, total = await service.list(
        actor, page=paging.page, page_size=paging.page_size, status=status, mine=mine
    )
    return PaginatedAPIResponse[CheckoutResponse](
        data=[_to_response(c) for c in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.post(
    "",
    response_model=APIResponse[CheckoutResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(ACCESS_USE))],
    summary="Check out an account",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def create_checkout(
    request: CheckoutCreate, service: CheckoutServiceDep, actor: ActorDep
) -> APIResponse[CheckoutResponse]:
    checkout = await service.checkout(
        actor,
        account_id=request.account_id,
        reason=request.reason,
        duration_minutes=request.duration_minutes,
        request_id=request.request_id,
    )
    return ok(_to_response(checkout))


@router.post(
    "/{checkout_id}/reveal",
    response_model=APIResponse[RevealedSecretResponse],
    dependencies=[Depends(require_permission(ACCESS_USE))],
    summary="Reveal the secret of your active check-out",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
    },
)
async def reveal(
    checkout_id: uuid.UUID, service: CheckoutServiceDep, actor: ActorDep, response: Response
) -> APIResponse[RevealedSecretResponse]:
    # POST, not GET: a reveal is an audited action, and must never be cached or prefetched.
    response.headers["Cache-Control"] = "no-store"
    secret = await service.reveal(actor, checkout_id)
    return ok(
        RevealedSecretResponse(
            checkout_id=secret.checkout_id,
            username=secret.username,
            secret_type=secret.secret_type,
            value=secret.value,
            expires_at=secret.expires_at,
        )
    )


@router.post(
    "/{checkout_id}/checkin",
    response_model=APIResponse[CheckoutResponse],
    dependencies=[Depends(require_permission(ACCESS_USE))],
    summary="Check in (holder) or revoke (admin) a check-out",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
    },
)
async def checkin(
    checkout_id: uuid.UUID, service: CheckoutServiceDep, actor: ActorDep
) -> APIResponse[CheckoutResponse]:
    return ok(_to_response(await service.checkin(actor, checkout_id)))
