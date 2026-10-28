"""Break-glass router.

POST /accounts/{account_id}/emergency-reveal — reveal any account's secret with a reason
(access.emergency; audited as secret.emergency_reveal, raises a high alert)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from src.contracts.schemas.requests.access.emergency_requests import EmergencyRevealRequest
from src.contracts.schemas.responses.access.checkout_responses import RevealedSecretResponse
from src.contracts.schemas.responses.common import (
    CONFLICT_RESPONSE,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
    APIResponse,
    ok,
)
from src.core.permissions import ACCESS_EMERGENCY
from src.dependencies.access import EmergencyAccessServiceDep
from src.dependencies.auth import ActorDep, require_permission

router = APIRouter(prefix="/accounts", tags=["access"])


@router.post(
    "/{account_id}/emergency-reveal",
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
        ),
        "Emergency reveal recorded and alerted",
    )
