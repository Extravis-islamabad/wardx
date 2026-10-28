"""TLS certificate pins (MikroTik API-SSL), the second half of a target's Host key flow.

POST /targets/{target_id}/tls-cert/probe   — read the certificate a target presents now
POST /targets/{target_id}/tls-cert/accept  — pin it after comparing the fingerprint
POST /targets/{target_id}/tls-cert/reset   — clear the pin (a recorded mismatch stays)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from src.contracts.schemas.requests.sessions.host_key_requests import TlsCertAccept
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
from src.contracts.schemas.responses.sessions.session_responses import TlsCertProbeResponse
from src.core.permissions import INVENTORY_MANAGE
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.sessions import TlsCertServiceDep
from src.routers.v1.inventory.targets import target_response

router = APIRouter(tags=["sessions"])

_ERRORS = {**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE, **CONFLICT_RESPONSE}


@router.post(
    "/targets/{target_id}/tls-cert/probe",
    response_model=APIResponse[TlsCertProbeResponse],
    dependencies=[Depends(require_permission(INVENTORY_MANAGE))],
    summary="Read the API-SSL certificate a target presents now (no login, nothing pinned)",
    responses=_ERRORS,
)
async def probe_tls_cert(
    target_id: uuid.UUID, service: TlsCertServiceDep, actor: ActorDep
) -> APIResponse[TlsCertProbeResponse]:
    probe = await service.probe(actor, target_id)
    return ok(
        TlsCertProbeResponse(
            target_id=probe.target_id,
            presented_fingerprint=probe.presented_fingerprint,
            subject=probe.subject,
            not_after=probe.not_after,
            pinned_fingerprint=probe.pinned_fingerprint,
            matches_pin=probe.matches_pin,
            mismatch_at=probe.mismatch_at,
            mismatch_fingerprint=probe.mismatch_fingerprint,
        )
    )


@router.post(
    "/targets/{target_id}/tls-cert/accept",
    response_model=APIResponse[TargetResponse],
    dependencies=[Depends(require_permission(INVENTORY_MANAGE))],
    summary="Pin the presented certificate after comparing its fingerprint with the device",
    responses={**_ERRORS, **VALIDATION_ERROR_RESPONSE},
)
async def accept_tls_cert(
    target_id: uuid.UUID, request: TlsCertAccept, service: TlsCertServiceDep, actor: ActorDep
) -> APIResponse[TargetResponse]:
    target = await service.accept(actor, target_id, request.fingerprint)
    return ok(target_response(target), f"Pinned {target.tls_cert_fingerprint}")


@router.post(
    "/targets/{target_id}/tls-cert/reset",
    response_model=APIResponse[TargetResponse],
    dependencies=[Depends(require_permission(INVENTORY_MANAGE))],
    summary="Clear a target's pinned API-SSL certificate (a recorded mismatch stays)",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def reset_tls_cert(
    target_id: uuid.UUID, service: TlsCertServiceDep, actor: ActorDep
) -> APIResponse[TargetResponse]:
    target = await service.reset(actor, target_id)
    return ok(target_response(target), "Certificate pin cleared; accept one before rotating")
