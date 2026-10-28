"""Gateway router — what the console shows about connecting, and host-key pins.

GET  /gateway/info                         — gateway host, port and login format
POST /targets/{target_id}/host-key/reset   — clear a target's pinned SSH host key
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from src.contracts.dto.inventory.target_dto import TargetDTO
from src.contracts.schemas.responses.common import (
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    APIResponse,
    ok,
)
from src.contracts.schemas.responses.inventory.target_responses import TargetResponse
from src.contracts.schemas.responses.sessions.session_responses import GatewayInfoResponse
from src.core.config import get_settings
from src.core.permissions import ACCESS_USE, INVENTORY_MANAGE
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.sessions import HostKeyServiceDep
from src.gateway.naming import SEPARATOR

router = APIRouter(tags=["sessions"])


def _target_response(dto: TargetDTO) -> TargetResponse:
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
    )


@router.get(
    "/gateway/info",
    response_model=APIResponse[GatewayInfoResponse],
    dependencies=[Depends(require_permission(ACCESS_USE))],
    summary="How to connect through the SSH gateway",
    responses={**UNAUTHORIZED_RESPONSE},
)
async def gateway_info() -> APIResponse[GatewayInfoResponse]:
    s = get_settings()
    return ok(
        GatewayInfoResponse(
            host=s.gateway_public_host,
            port=s.gateway_port,
            login_format=f"<you>{SEPARATOR}<account>{SEPARATOR}<target>",
        )
    )


@router.post(
    "/targets/{target_id}/host-key/reset",
    response_model=APIResponse[TargetResponse],
    dependencies=[Depends(require_permission(INVENTORY_MANAGE))],
    summary="Clear a target's pinned SSH host key",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def reset_host_key(
    target_id: uuid.UUID, service: HostKeyServiceDep, actor: ActorDep
) -> APIResponse[TargetResponse]:
    target = await service.reset(actor, target_id)
    return ok(_target_response(target), "Host key cleared; the next session pins a new one")
