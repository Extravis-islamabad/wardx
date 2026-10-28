"""Account rotation router.

GET  /accounts/{account_id}/rotation          — status, effective policy, job history
POST /accounts/{account_id}/rotate            — rotate now (manage_accounts; reason)
POST /accounts/{account_id}/verify            — verify now
POST /accounts/{account_id}/reconcile         — reconcile through the reconcile account
POST /accounts/{account_id}/rotation/confirm  — attest an untrustworthy verify
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from src.contracts.schemas.requests.rotation.rotation_requests import (
    ConfirmIn,
    RotateIn,
    RotationRequestIn,
)
from src.contracts.schemas.responses.common import (
    CONFLICT_RESPONSE,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
    APIResponse,
    ok,
)
from src.contracts.schemas.responses.rotation.rotation_responses import (
    AccountRotationResponse,
    RotationJobResponse,
)
from src.core.config import get_settings
from src.core.permissions import INVENTORY_MANAGE, INVENTORY_VIEW
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.rotation import RotationReviewServiceDep, RotationServiceDep
from src.routers.v1.rotation.mappers import job_response, policy_response

router = APIRouter(prefix="/accounts/{account_id}", tags=["rotation"])

_WRITE_RESPONSES = {
    **UNAUTHORIZED_RESPONSE,
    **FORBIDDEN_RESPONSE,
    **NOT_FOUND_RESPONSE,
    **CONFLICT_RESPONSE,
    **VALIDATION_ERROR_RESPONSE,
}


@router.get(
    "/rotation",
    response_model=APIResponse[AccountRotationResponse],
    dependencies=[Depends(require_permission(INVENTORY_VIEW))],
    summary="An account's rotation status, policy and job history",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def account_rotation(
    account_id: uuid.UUID, service: RotationServiceDep, actor: ActorDep
) -> APIResponse[AccountRotationResponse]:
    v = await service.account_rotation(actor, account_id)
    a, t = v.account, v.target
    return ok(
        AccountRotationResponse(
            account_id=a.id,
            username=a.username,
            target_name=t.name,
            platform=t.platform,
            protocol=t.protocol,
            sync_status=a.sync_status,
            rotation_status=a.rotation_status,
            last_rotated_at=a.last_rotated_at,
            last_rotation_status=a.last_rotation_status,
            last_verified_at=a.last_verified_at,
            last_verify_method=a.last_verify_method,
            risk_flags=a.risk_flags,
            risk_accepted_by=a.risk_accepted_by,
            risk_accepted_at=a.risk_accepted_at,
            risk_accepted_reason=a.risk_accepted_reason,
            reconcile_account_id=a.reconcile_account_id,
            rotation_allowed=t.rotation_allowed,
            rotation_enabled=get_settings().rotation_enabled,
            host_key_pinned=bool(t.ssh_host_key),
            non_rotatable_reason=v.non_rotatable_reason,
            effective_policy=v.effective_policy,
            policy_error=v.policy_error,
            effective_interval_days=v.effective_interval_days,
            effective_rotate_after_use=v.effective_rotate_after_use,
            safe_policy=policy_response(v.safe_policy),
            open_job=job_response(v.open_job) if v.open_job else None,
            jobs=[job_response(j) for j in v.jobs],
        )
    )


async def _queue(service, actor, account_id, operation, reason, dry_run=False):
    job = await service.request(actor, account_id, operation, reason, dry_run=dry_run)
    return ok(job_response(job), f"{operation.capitalize()} queued")


@router.post(
    "/rotate",
    response_model=APIResponse[RotationJobResponse],
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission(INVENTORY_MANAGE))],
    summary="Rotate an account's password now (queued; runs when every holder released it)",
    responses=_WRITE_RESPONSES,
)
async def rotate(
    account_id: uuid.UUID, request: RotateIn, service: RotationServiceDep, actor: ActorDep
) -> APIResponse[RotationJobResponse]:
    return await _queue(service, actor, account_id, "rotate", request.reason, request.dry_run)


@router.post(
    "/verify",
    response_model=APIResponse[RotationJobResponse],
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission(INVENTORY_MANAGE))],
    summary="Verify an account's password on the device now",
    responses=_WRITE_RESPONSES,
)
async def verify(
    account_id: uuid.UUID, request: RotationRequestIn, service: RotationServiceDep, actor: ActorDep
) -> APIResponse[RotationJobResponse]:
    return await _queue(service, actor, account_id, "verify", request.reason)


@router.post(
    "/reconcile",
    response_model=APIResponse[RotationJobResponse],
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission(INVENTORY_MANAGE))],
    summary="Set a new password through the account's reconcile account",
    responses=_WRITE_RESPONSES,
)
async def reconcile(
    account_id: uuid.UUID, request: RotationRequestIn, service: RotationServiceDep, actor: ActorDep
) -> APIResponse[RotationJobResponse]:
    return await _queue(service, actor, account_id, "reconcile", request.reason)


@router.post(
    "/rotation/confirm",
    response_model=APIResponse[None],
    dependencies=[Depends(require_permission(INVENTORY_MANAGE))],
    summary="Confirm an untrustworthy verify (risk accepted, with a written reason)",
    responses=_WRITE_RESPONSES,
)
async def confirm(
    account_id: uuid.UUID, request: ConfirmIn, service: RotationReviewServiceDep, actor: ActorDep
) -> APIResponse[None]:
    await service.confirm(actor, account_id, request.reason)
    return ok(None, "Confirmed: risk accepted; listed until a later clean verify")
