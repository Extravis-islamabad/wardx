"""Safe rotation policy router.

GET /safes/{safe_id}/rotation-policy — the safe's rotation policy (safes.manage, or 'list')
PUT /safes/{safe_id}/rotation-policy — replace it (safes.manage; audited)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from src.contracts.schemas.requests.rotation.rotation_requests import SafeRotationPolicyIn
from src.contracts.schemas.responses.common import (
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
    APIResponse,
    ok,
)
from src.contracts.schemas.responses.rotation.rotation_responses import (
    SafeRotationPolicyResponse,
)
from src.core.permissions import INVENTORY_VIEW, SAFES_MANAGE
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.rotation import SafeRotationPolicyServiceDep
from src.routers.v1.rotation.mappers import policy_response

router = APIRouter(prefix="/safes/{safe_id}/rotation-policy", tags=["rotation"])


@router.get(
    "",
    response_model=APIResponse[SafeRotationPolicyResponse],
    dependencies=[Depends(require_permission(INVENTORY_VIEW))],
    summary="Get a safe's rotation policy",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def get_policy(
    safe_id: uuid.UUID, service: SafeRotationPolicyServiceDep, actor: ActorDep
) -> APIResponse[SafeRotationPolicyResponse]:
    return ok(policy_response(await service.get(actor, safe_id)))


@router.put(
    "",
    response_model=APIResponse[SafeRotationPolicyResponse],
    dependencies=[Depends(require_permission(SAFES_MANAGE))],
    summary="Replace a safe's rotation policy",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def save_policy(
    safe_id: uuid.UUID,
    request: SafeRotationPolicyIn,
    service: SafeRotationPolicyServiceDep,
    actor: ActorDep,
) -> APIResponse[SafeRotationPolicyResponse]:
    return ok(policy_response(await service.save(actor, safe_id, request.model_dump())), "Saved")
