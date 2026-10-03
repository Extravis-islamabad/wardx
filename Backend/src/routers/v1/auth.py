from __future__ import annotations

from fastapi import APIRouter, Request

from src.contracts.schemas.common import APIResponse, ok
from src.contracts.schemas.identity import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResult,
    MfaCode,
    MfaRecoveryCodes,
    MfaSetup,
    MfaStatusOut,
    MfaVerifyRequest,
    RefreshRequest,
    TokenPair,
    UserOut,
)
from src.core.config import get_settings
from src.dependencies.auth import ActorDep, CurrentUser, SessionDep, client_ip
from src.models import User
from src.services import auth_service, mfa_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=APIResponse[LoginResult])
async def login(body: LoginRequest, request: Request, session: SessionDep):
    tokens = await auth_service.login(
        session,
        get_settings(),
        username=body.username,
        password=body.password,
        source_ip=client_ip(request),
    )
    return ok(tokens)


@router.post("/refresh", response_model=APIResponse[TokenPair])
async def refresh(body: RefreshRequest, session: SessionDep):
    return ok(await auth_service.refresh(session, get_settings(), body.refresh_token))


@router.post("/logout", response_model=APIResponse[None])
async def logout(actor: ActorDep, session: SessionDep):
    await auth_service.logout_everywhere(session, actor)
    return ok(None, "Signed out of all sessions")


@router.get("/me", response_model=APIResponse[UserOut])
async def me(user: CurrentUser):
    return ok(UserOut.model_validate(user))


@router.post("/change-password", response_model=APIResponse[TokenPair])
async def change_password(body: ChangePasswordRequest, actor: ActorDep, session: SessionDep):
    tokens = await auth_service.change_password(
        session, get_settings(), actor, current=body.current_password, new=body.new_password
    )
    return ok(tokens, "Password changed; other sessions were signed out")


# ── MFA ──


@router.post("/mfa/verify", response_model=APIResponse[LoginResult])
async def mfa_verify(body: MfaVerifyRequest, request: Request, session: SessionDep):
    result = await auth_service.complete_mfa(
        session,
        get_settings(),
        mfa_token=body.mfa_token,
        code=body.code,
        source_ip=client_ip(request),
    )
    return ok(result)


@router.get("/mfa", response_model=APIResponse[MfaStatusOut])
async def mfa_status(user: CurrentUser, session: SessionDep):
    s = await mfa_service.status(session, get_settings(), user)
    return ok(MfaStatusOut(**s.__dict__))


@router.post("/mfa/setup", response_model=APIResponse[MfaSetup])
async def mfa_setup(actor: ActorDep, session: SessionDep):
    seed, uri = await mfa_service.start_enrolment(session, actor)
    return ok(MfaSetup(secret=seed, otpauth_uri=uri), "Scan the code, then confirm with a code")


@router.post("/mfa/enable", response_model=APIResponse[MfaRecoveryCodes])
async def mfa_enable(body: MfaCode, actor: ActorDep, session: SessionDep):
    codes = await mfa_service.confirm_enrolment(session, actor, body.code)
    user = await session.get(User, actor.id)
    tokens = auth_service.issue_tokens(user, get_settings())
    return ok(
        MfaRecoveryCodes(recovery_codes=codes, tokens=tokens),
        "MFA is on. Store the recovery codes somewhere safe; they are shown once.",
    )


@router.post("/mfa/recovery-codes", response_model=APIResponse[MfaRecoveryCodes])
async def mfa_new_recovery_codes(body: MfaCode, actor: ActorDep, session: SessionDep):
    codes = await mfa_service.regenerate_recovery_codes(session, actor, body.code)
    return ok(MfaRecoveryCodes(recovery_codes=codes), "Old recovery codes no longer work")


@router.post("/mfa/disable", response_model=APIResponse[None])
async def mfa_disable(body: MfaCode, actor: ActorDep, session: SessionDep):
    await mfa_service.disable_self(session, get_settings(), actor, body.code)
    return ok(None, "MFA is off")
