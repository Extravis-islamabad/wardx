"""Safe members router (safes.manage, or manage_members on the safe).

GET    /safes/{safe_id}/members               — the safe's members
POST   /safes/{safe_id}/members               — add a user, directory group (or role)
PATCH  /safes/{safe_id}/members/{member_id}   — change a member's permissions
DELETE /safes/{safe_id}/members/{member_id}   — remove a member

Nobody grants to themselves, a group they are in, or their own role
(403 ``self_grant_forbidden``). The route gate is inventory.view; the service
checks safes.manage or manage_members on the safe.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from src.contracts.dto.safes.safe_dto import SafeMemberDTO
from src.contracts.schemas.requests.safes.safe_requests import SafeMemberCreate, SafeMemberUpdate
from src.contracts.schemas.responses.common import (
    CONFLICT_RESPONSE,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
    APIResponse,
    ok,
)
from src.contracts.schemas.responses.safes.safe_responses import SafeMemberResponse
from src.core.permissions import INVENTORY_VIEW
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.safes import SafeServiceDep

router = APIRouter(prefix="/safes/{safe_id}/members", tags=["safes"])

_ERRORS = {
    **UNAUTHORIZED_RESPONSE,
    **FORBIDDEN_RESPONSE,
    **NOT_FOUND_RESPONSE,
    **CONFLICT_RESPONSE,
    **VALIDATION_ERROR_RESPONSE,
}


def _to_response(dto: SafeMemberDTO) -> SafeMemberResponse:
    return SafeMemberResponse(
        id=dto.id,
        safe_id=dto.safe_id,
        principal_type=dto.principal_type,
        principal_key=dto.principal_key,
        display_name=dto.display_name,
        permissions=list(dto.permissions),
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


@router.get(
    "",
    response_model=APIResponse[list[SafeMemberResponse]],
    dependencies=[Depends(require_permission(INVENTORY_VIEW))],
    summary="List a safe's members",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def list_members(
    safe_id: uuid.UUID, service: SafeServiceDep, actor: ActorDep
) -> APIResponse[list[SafeMemberResponse]]:
    return ok([_to_response(m) for m in await service.list_members(actor, safe_id)])


@router.post(
    "",
    response_model=APIResponse[SafeMemberResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(INVENTORY_VIEW))],
    summary="Add a member to a safe",
    responses=_ERRORS,
)
async def add_member(
    safe_id: uuid.UUID, request: SafeMemberCreate, service: SafeServiceDep, actor: ActorDep
) -> APIResponse[SafeMemberResponse]:
    member = await service.add_member(
        actor,
        safe_id,
        principal_type=request.principal_type,
        principal_key=request.principal_key,
        permissions=request.permissions,
    )
    return ok(_to_response(member))


@router.patch(
    "/{member_id}",
    response_model=APIResponse[SafeMemberResponse],
    dependencies=[Depends(require_permission(INVENTORY_VIEW))],
    summary="Change a member's permissions",
    responses=_ERRORS,
)
async def update_member(
    safe_id: uuid.UUID,
    member_id: uuid.UUID,
    request: SafeMemberUpdate,
    service: SafeServiceDep,
    actor: ActorDep,
) -> APIResponse[SafeMemberResponse]:
    member = await service.update_member(actor, safe_id, member_id, permissions=request.permissions)
    return ok(_to_response(member))


@router.delete(
    "/{member_id}",
    response_model=APIResponse[None],
    dependencies=[Depends(require_permission(INVENTORY_VIEW))],
    summary="Remove a member from a safe",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def remove_member(
    safe_id: uuid.UUID, member_id: uuid.UUID, service: SafeServiceDep, actor: ActorDep
) -> APIResponse[None]:
    await service.remove_member(actor, safe_id, member_id)
    return ok(None, "Member removed")
