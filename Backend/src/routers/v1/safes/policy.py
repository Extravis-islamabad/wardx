"""Safe approval policy router.

GET /safes/{safe_id}/policy — the safe's approval policy (safes.manage, or 'list' on it)
PUT /safes/{safe_id}/policy — replace it, levels included (safes.manage; audited)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from src.contracts.dto.safes.approval_policy_dto import ApprovalPolicyDTO
from src.contracts.schemas.requests.safes.safe_requests import ApprovalPolicyIn
from src.contracts.schemas.responses.common import (
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
    APIResponse,
    ok,
)
from src.contracts.schemas.responses.safes.safe_responses import (
    ApprovalLevelResponse,
    ApprovalPolicyResponse,
)
from src.core.permissions import INVENTORY_VIEW, SAFES_MANAGE
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.safes import ApprovalPolicyServiceDep

router = APIRouter(prefix="/safes/{safe_id}/policy", tags=["safes"])


def policy_response(dto: ApprovalPolicyDTO) -> ApprovalPolicyResponse:
    return ApprovalPolicyResponse(
        safe_id=dto.safe_id,
        approval_required=dto.approval_required,
        levels=[
            ApprovalLevelResponse(
                position=lv.position,
                required_approvals=lv.required_approvals,
                approver_type=lv.approver_type,
                approver_key=lv.approver_key,
            )
            for lv in dto.levels
        ],
        ticket_mode=dto.ticket_mode,
        ticket_pattern=dto.ticket_pattern,
        approval_window_minutes=dto.approval_window_minutes,
        approval_multi_use=dto.approval_multi_use,
        level_timeout_hours=dto.level_timeout_hours,
    )


@router.get(
    "",
    response_model=APIResponse[ApprovalPolicyResponse],
    dependencies=[Depends(require_permission(INVENTORY_VIEW))],
    summary="Get a safe's approval policy",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def get_policy(
    safe_id: uuid.UUID, service: ApprovalPolicyServiceDep, actor: ActorDep
) -> APIResponse[ApprovalPolicyResponse]:
    return ok(policy_response(await service.get(actor, safe_id)))


@router.put(
    "",
    response_model=APIResponse[ApprovalPolicyResponse],
    dependencies=[Depends(require_permission(SAFES_MANAGE))],
    summary="Replace a safe's approval policy",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def save_policy(
    safe_id: uuid.UUID,
    request: ApprovalPolicyIn,
    service: ApprovalPolicyServiceDep,
    actor: ActorDep,
) -> APIResponse[ApprovalPolicyResponse]:
    values = request.model_dump(exclude={"levels"})
    levels = [lv.model_dump(mode="json") for lv in request.levels]
    return ok(policy_response(await service.save(actor, safe_id, values, levels)), "Policy saved")
