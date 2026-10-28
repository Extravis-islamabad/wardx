"""Targets router — devices, hosts and databases that privileged accounts live on.

GET    /targets              — page through targets (search, platform)
GET    /targets/{target_id}  — one target
POST   /targets              — add a target (port defaults from the protocol)
PATCH  /targets/{target_id}  — change a target
DELETE /targets/{target_id}  — delete a target, its accounts and their secrets
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from src.contracts.dto.inventory.target_dto import TargetDTO, TargetFilterDTO
from src.contracts.schemas.requests.common import PageParams
from src.contracts.schemas.requests.inventory.target_requests import TargetCreate, TargetUpdate
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
from src.contracts.schemas.responses.inventory.target_responses import TargetResponse
from src.core.enums import Platform
from src.core.permissions import INVENTORY_MANAGE, INVENTORY_VIEW
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.inventory import TargetServiceDep
from src.services.rotation.rotation_service import non_rotatable_reason

router = APIRouter(prefix="/targets", tags=["inventory"])


def target_response(dto: TargetDTO) -> TargetResponse:
    """Shared with the gateway router (host-key pins)."""
    return TargetResponse(
        id=dto.id,
        name=dto.name,
        address=dto.address,
        platform=dto.platform,
        protocol=dto.protocol,
        port=dto.port,
        description=dto.description,
        tags=dto.tags,
        external_ref=dto.external_ref,
        is_active=dto.is_active,
        ssh_host_key_fingerprint=dto.ssh_host_key_fingerprint,
        ssh_host_key_learned_at=dto.ssh_host_key_learned_at,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
        rotation_allowed=dto.rotation_allowed,
        policy_overrides=dto.policy_overrides or {},
        non_rotatable_reason=non_rotatable_reason(dto.protocol, dto.platform),
    )


@router.get(
    "",
    response_model=PaginatedAPIResponse[TargetResponse],
    dependencies=[Depends(require_permission(INVENTORY_VIEW))],
    summary="List targets",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def list_targets(
    service: TargetServiceDep,
    paging: Annotated[PageParams, Depends()],
    search: Annotated[str | None, Query(max_length=100)] = None,
    platform: Platform | None = None,
) -> PaginatedAPIResponse[TargetResponse]:
    rows, total = await service.list(
        TargetFilterDTO(search=search, platform=platform),
        page=paging.page,
        page_size=paging.page_size,
    )
    return PaginatedAPIResponse[TargetResponse](
        data=[target_response(t) for t in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.get(
    "/{target_id}",
    response_model=APIResponse[TargetResponse],
    dependencies=[Depends(require_permission(INVENTORY_VIEW))],
    summary="Get a target",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def get_target(
    target_id: uuid.UUID, service: TargetServiceDep
) -> APIResponse[TargetResponse]:
    return ok(target_response(await service.get(target_id)))


@router.post(
    "",
    response_model=APIResponse[TargetResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(INVENTORY_MANAGE))],
    summary="Create a target",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def create_target(
    request: TargetCreate, service: TargetServiceDep, actor: ActorDep
) -> APIResponse[TargetResponse]:
    values = request.model_dump()
    values["policy_overrides"] = (
        request.policy_overrides.model_dump(exclude_none=True) if (request.policy_overrides) else {}
    )
    return ok(target_response(await service.create(actor, values)))


@router.patch(
    "/{target_id}",
    response_model=APIResponse[TargetResponse],
    dependencies=[Depends(require_permission(INVENTORY_MANAGE))],
    summary="Update a target",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def update_target(
    target_id: uuid.UUID, request: TargetUpdate, service: TargetServiceDep, actor: ActorDep
) -> APIResponse[TargetResponse]:
    changes = request.model_dump(exclude_unset=True)
    if "policy_overrides" in changes:
        overrides = request.policy_overrides
        changes["policy_overrides"] = overrides.model_dump(exclude_none=True) if overrides else {}
    return ok(target_response(await service.update(actor, target_id, changes)))


@router.delete(
    "/{target_id}",
    response_model=APIResponse[None],
    dependencies=[Depends(require_permission(INVENTORY_MANAGE))],
    summary="Delete a target with its accounts and secrets",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
    },
)
async def delete_target(
    target_id: uuid.UUID, service: TargetServiceDep, actor: ActorDep
) -> APIResponse[None]:
    await service.delete(actor, target_id)
    return ok(None, "Target and its accounts deleted")
