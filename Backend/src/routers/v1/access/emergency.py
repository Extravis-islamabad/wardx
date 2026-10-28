"""Break-glass router (access.emergency).

GET  /emergency/accounts                     — every account, whatever its safe, to pick
                                               one in an emergency (no secrets; audited)
POST /accounts/{account_id}/emergency-reveal — reveal any account's secret with a reason
                                               (audited as secret.emergency_reveal, high alert)
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.contracts.dto.inventory.account_dto import AccountFilterDTO
from src.contracts.schemas.requests.access.emergency_requests import EmergencyRevealRequest
from src.contracts.schemas.requests.common import PageParams
from src.contracts.schemas.responses.access.checkout_responses import RevealedSecretResponse
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
from src.contracts.schemas.responses.inventory.account_responses import AccountResponse
from src.core.permissions import ACCESS_EMERGENCY
from src.dependencies.access import EmergencyAccessServiceDep
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.inventory import AccountServiceDep
from src.routers.v1.inventory.accounts import account_response

router = APIRouter(tags=["access"])


@router.get(
    "/emergency/accounts",
    response_model=PaginatedAPIResponse[AccountResponse],
    dependencies=[Depends(require_permission(ACCESS_EMERGENCY))],
    summary="Break-glass: every account, whatever its safe (no secrets)",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def emergency_accounts(
    service: AccountServiceDep,
    actor: ActorDep,
    paging: Annotated[PageParams, Depends()],
    search: Annotated[str | None, Query(max_length=100)] = None,
    reason: Annotated[str | None, Query(max_length=2000)] = None,
) -> PaginatedAPIResponse[AccountResponse]:
    rows, total = await service.list_any_safe(
        actor,
        AccountFilterDTO(search=search),
        page=paging.page,
        page_size=paging.page_size,
        reason=reason,
    )
    return PaginatedAPIResponse[AccountResponse](
        data=[account_response(a) for a in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.post(
    "/accounts/{account_id}/emergency-reveal",
    response_model=APIResponse[RevealedSecretResponse],
    dependencies=[Depends(require_permission(ACCESS_EMERGENCY))],
    summary="Break-glass: reveal an account's secret regardless of safe membership",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def emergency_reveal(
    account_id: uuid.UUID,
    request: EmergencyRevealRequest,
    service: EmergencyAccessServiceDep,
    actor: ActorDep,
) -> APIResponse[RevealedSecretResponse]:
    secret = await service.reveal(actor, account_id, request.reason)
    return ok(
        RevealedSecretResponse(
            checkout_id=secret.checkout_id,
            username=secret.username,
            secret_type=secret.secret_type,
            value=secret.value,
            expires_at=secret.expires_at,
            notice=secret.notice,
        ),
        "Emergency reveal recorded and alerted",
    )
