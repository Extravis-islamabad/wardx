"""MFA router — the second sign-in step and managing your own TOTP.

POST /auth/mfa/verify           — complete sign-in with a TOTP or recovery code
GET  /auth/mfa                  — your MFA status
POST /auth/mfa/setup            — start enrolment (new seed)
POST /auth/mfa/enable           — confirm enrolment; returns recovery codes and fresh tokens
POST /auth/mfa/recovery-codes   — replace your recovery codes
POST /auth/mfa/disable          — turn MFA off (when your role allows)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from src.contracts.schemas.requests.identity.auth_requests import MfaCode, MfaVerifyRequest
from src.contracts.schemas.responses.common import (
    CONFLICT_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
    APIResponse,
    ok,
)
from src.contracts.schemas.responses.identity.auth_responses import (
    LoginResultResponse,
    MfaRecoveryCodesResponse,
    MfaSetupResponse,
    MfaStatusResponse,
)
from src.core.permissions import PROFILE_SELF
from src.dependencies.auth import ActorDep, CurrentUserDep, client_ip, require_permission
from src.dependencies.identity import AuthServiceDep, MfaServiceDep
from src.routers.v1.identity.mappers import login_response, token_response

router = APIRouter(prefix="/auth/mfa", tags=["auth"])


@router.post(
    "/verify",
    response_model=APIResponse[LoginResultResponse],
    summary="Complete sign-in with an MFA code",
    responses={**UNAUTHORIZED_RESPONSE, **VALIDATION_ERROR_RESPONSE},
)
async def mfa_verify(
    request: MfaVerifyRequest, http_request: Request, service: AuthServiceDep
) -> APIResponse[LoginResultResponse]:
    result = await service.complete_mfa(
        mfa_token=request.mfa_token, code=request.code, source_ip=client_ip(http_request)
    )
    return ok(login_response(result))


@router.get(
    "",
    response_model=APIResponse[MfaStatusResponse],
    dependencies=[Depends(require_permission(PROFILE_SELF))],
    summary="Your MFA status",
    responses={**UNAUTHORIZED_RESPONSE},
)
async def mfa_status(
    user: CurrentUserDep, service: MfaServiceDep
) -> APIResponse[MfaStatusResponse]:
    s = await service.status(user.id, user.role)
    return ok(
        MfaStatusResponse(
            enabled=s.enabled,
            pending=s.pending,
            required=s.required,
            recovery_codes_left=s.recovery_codes_left,
        )
    )


@router.post(
    "/setup",
    response_model=APIResponse[MfaSetupResponse],
    dependencies=[Depends(require_permission(PROFILE_SELF))],
    summary="Start MFA enrolment",
    responses={**UNAUTHORIZED_RESPONSE, **CONFLICT_RESPONSE},
)
async def mfa_setup(service: MfaServiceDep, actor: ActorDep) -> APIResponse[MfaSetupResponse]:
    seed, uri = await service.start_enrolment(actor)
    return ok(
        MfaSetupResponse(secret=seed, otpauth_uri=uri), "Scan the code, then confirm with a code"
    )


@router.post(
    "/enable",
    response_model=APIResponse[MfaRecoveryCodesResponse],
    dependencies=[Depends(require_permission(PROFILE_SELF))],
    summary="Confirm MFA enrolment",
    responses={**UNAUTHORIZED_RESPONSE, **CONFLICT_RESPONSE, **VALIDATION_ERROR_RESPONSE},
)
async def mfa_enable(
    request: MfaCode, service: MfaServiceDep, auth: AuthServiceDep, actor: ActorDep
) -> APIResponse[MfaRecoveryCodesResponse]:
    codes = await service.confirm_enrolment(actor, request.code)
    tokens = await auth.tokens_for(actor.id)
    return ok(
        MfaRecoveryCodesResponse(recovery_codes=codes, tokens=token_response(tokens)),
        "MFA is on. Store the recovery codes somewhere safe; they are shown once.",
    )


@router.post(
    "/recovery-codes",
    response_model=APIResponse[MfaRecoveryCodesResponse],
    dependencies=[Depends(require_permission(PROFILE_SELF))],
    summary="Replace your recovery codes",
    responses={**UNAUTHORIZED_RESPONSE, **VALIDATION_ERROR_RESPONSE},
)
async def mfa_new_recovery_codes(
    request: MfaCode, service: MfaServiceDep, actor: ActorDep
) -> APIResponse[MfaRecoveryCodesResponse]:
    codes = await service.regenerate_recovery_codes(actor, request.code)
    return ok(MfaRecoveryCodesResponse(recovery_codes=codes), "Old recovery codes no longer work")


@router.post(
    "/disable",
    response_model=APIResponse[None],
    dependencies=[Depends(require_permission(PROFILE_SELF))],
    summary="Turn MFA off",
    responses={**UNAUTHORIZED_RESPONSE, **CONFLICT_RESPONSE, **VALIDATION_ERROR_RESPONSE},
)
async def mfa_disable(
    request: MfaCode, service: MfaServiceDep, actor: ActorDep
) -> APIResponse[None]:
    await service.disable_self(actor, request.code)
    return ok(None, "MFA is off")
