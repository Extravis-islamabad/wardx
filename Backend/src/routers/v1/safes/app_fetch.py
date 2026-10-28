"""A safe's credential-provider settings (docs/phase1/CREDENTIAL_PROVIDER.md §3, §4).

GET /safes/{safe_id}/app-fetch — allow_app_fetch and app_cache_seconds ('list' or safes.manage)
PUT /safes/{safe_id}/app-fetch — change them ('manage_members' or safes.manage; audited)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from src.contracts.dto.safes.safe_dto import SafeDTO
from src.contracts.schemas.requests.safes.safe_requests import SafeAppFetchIn
from src.contracts.schemas.responses.common import (
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
    APIResponse,
    ok,
)
from src.contracts.schemas.responses.safes.safe_responses import SafeAppFetchResponse
from src.core.permissions import INVENTORY_VIEW
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.safes import SafeAppFetchServiceDep

router = APIRouter(prefix="/safes/{safe_id}/app-fetch", tags=["safes"])


def _to_response(dto: SafeDTO) -> SafeAppFetchResponse:
    return SafeAppFetchResponse(
        safe_id=dto.id,
        approval_required=dto.approval_required,
        allow_app_fetch=dto.allow_app_fetch,
        app_cache_seconds=dto.app_cache_seconds,
    )


@router.get(
    "",
    response_model=APIResponse[SafeAppFetchResponse],
    dependencies=[Depends(require_permission(INVENTORY_VIEW))],
    summary="Get a safe's credential-provider settings",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def get_app_fetch(
    safe_id: uuid.UUID, service: SafeAppFetchServiceDep, actor: ActorDep
) -> APIResponse[SafeAppFetchResponse]:
    return ok(_to_response(await service.get(actor, safe_id)))


@router.put(
    "",
    response_model=APIResponse[SafeAppFetchResponse],
    dependencies=[Depends(require_permission(INVENTORY_VIEW))],
    summary="Change a safe's credential-provider settings",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def save_app_fetch(
    safe_id: uuid.UUID, request: SafeAppFetchIn, service: SafeAppFetchServiceDep, actor: ActorDep
) -> APIResponse[SafeAppFetchResponse]:
    return ok(_to_response(await service.save(actor, safe_id, request.model_dump())), "Saved")
