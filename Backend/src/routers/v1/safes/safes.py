"""Safes router.

GET   /safes              — safes the caller can list (every safe with safes.manage)
GET   /safes/{safe_id}    — one safe
POST  /safes              — create a safe (safes.manage)
PATCH /safes/{safe_id}    — rename, describe, activate or deactivate (safes.manage)
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from src.contracts.dto.safes.safe_dto import SafeDTO
from src.contracts.schemas.requests.common import PageParams
from src.contracts.schemas.requests.safes.safe_requests import SafeCreate, SafeUpdate
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
from src.contracts.schemas.responses.safes.safe_responses import SafeResponse
from src.core.permissions import INVENTORY_VIEW, SAFES_MANAGE
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.safes import SafeServiceDep

router = APIRouter(prefix="/safes", tags=["safes"])


def _to_response(dto: SafeDTO, perms: frozenset[str] = frozenset()) -> SafeResponse:
    return SafeResponse(
        id=dto.id,
        name=dto.name,
        description=dto.description,
        is_active=dto.is_active,
        account_count=dto.account_count,
        member_count=dto.member_count,
        my_permissions=sorted(perms),
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


@router.get(
    "",
    response_model=PaginatedAPIResponse[SafeResponse],
    dependencies=[Depends(require_permission(INVENTORY_VIEW))],
    summary="List safes",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def list_safes(
    service: SafeServiceDep,
    actor: ActorDep,
    paging: Annotated[PageParams, Depends()],
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> PaginatedAPIResponse[SafeResponse]:
    rows, total = await service.list(
        actor, search=search, page=paging.page, page_size=paging.page_size
    )
    perms = await service.my_permissions(actor)
    return PaginatedAPIResponse[SafeResponse](
        data=[_to_response(s, perms.get(s.id, frozenset())) for s in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.get(
    "/{safe_id}",
    response_model=APIResponse[SafeResponse],
    dependencies=[Depends(require_permission(INVENTORY_VIEW))],
    summary="Get a safe",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def get_safe(
    safe_id: uuid.UUID, service: SafeServiceDep, actor: ActorDep
) -> APIResponse[SafeResponse]:
    safe = await service.get(actor, safe_id)
    perms = await service.my_permissions(actor)
    return ok(_to_response(safe, perms.get(safe.id, frozenset())))


@router.post(
    "",
    response_model=APIResponse[SafeResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(SAFES_MANAGE))],
    summary="Create a safe",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def create_safe(
    request: SafeCreate, service: SafeServiceDep, actor: ActorDep
) -> APIResponse[SafeResponse]:
    return ok(_to_response(await service.create(actor, request.model_dump())))


@router.patch(
    "/{safe_id}",
    response_model=APIResponse[SafeResponse],
    dependencies=[Depends(require_permission(SAFES_MANAGE))],
    summary="Update a safe",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def update_safe(
    safe_id: uuid.UUID, request: SafeUpdate, service: SafeServiceDep, actor: ActorDep
) -> APIResponse[SafeResponse]:
    changes = {k: v for k, v in request.model_dump(exclude_unset=True).items() if v is not None}
    safe = await service.update(actor, safe_id, changes)
    perms = await service.my_permissions(actor)
    return ok(_to_response(safe, perms.get(safe.id, frozenset())))
