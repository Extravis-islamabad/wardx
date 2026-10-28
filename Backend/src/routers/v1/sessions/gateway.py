"""Gateway router — what the console shows about connecting, and host-key pins.

GET  /gateway/info                         — gateway host, port and login format
POST /targets/{target_id}/host-key/reset   — clear a target's pinned SSH host key
POST /targets/{target_id}/host-key/probe   — read the key a target presents now (no login)
POST /targets/{target_id}/host-key/accept  — pin it after comparing the fingerprint
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from src.contracts.schemas.requests.sessions.host_key_requests import HostKeyAccept
from src.contracts.schemas.responses.common import (
    CONFLICT_RESPONSE,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
    APIResponse,
    ok,
)
from src.contracts.schemas.responses.inventory.target_responses import TargetResponse
from src.contracts.schemas.responses.sessions.session_responses import (
    GatewayInfoResponse,
    HostKeyProbeResponse,
)
from src.core.config import get_settings
from src.core.permissions import ACCESS_USE, INVENTORY_MANAGE
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.sessions import HostKeyServiceDep
from src.gateway.naming import SEPARATOR
from src.routers.v1.inventory.targets import target_response

router = APIRouter(tags=["sessions"])


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
    return ok(target_response(target), "Host key cleared; the next session pins a new one")


@router.post(
    "/targets/{target_id}/host-key/probe",
    response_model=APIResponse[HostKeyProbeResponse],
    dependencies=[Depends(require_permission(INVENTORY_MANAGE))],
    summary="Read the SSH host key a target presents now (no login, nothing pinned)",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
    },
)
async def probe_host_key(
    target_id: uuid.UUID, service: HostKeyServiceDep, actor: ActorDep
) -> APIResponse[HostKeyProbeResponse]:
    probe = await service.probe(actor, target_id)
    return ok(
        HostKeyProbeResponse(
            target_id=probe.target_id,
            presented_fingerprint=probe.presented_fingerprint,
            key_type=probe.key_type,
            pinned_fingerprint=probe.pinned_fingerprint,
            matches_pin=probe.matches_pin,
            mismatch_at=probe.mismatch_at,
            mismatch_fingerprint=probe.mismatch_fingerprint,
        )
    )


@router.post(
    "/targets/{target_id}/host-key/accept",
    response_model=APIResponse[TargetResponse],
    dependencies=[Depends(require_permission(INVENTORY_MANAGE))],
    summary="Pin the presented key after comparing its fingerprint with the device",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def accept_host_key(
    target_id: uuid.UUID, request: HostKeyAccept, service: HostKeyServiceDep, actor: ActorDep
) -> APIResponse[TargetResponse]:
    target = await service.accept(actor, target_id, request.fingerprint)
    return ok(target_response(target), f"Pinned {target.ssh_host_key_fingerprint}")
