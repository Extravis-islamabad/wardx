"""Sign-in router.

POST /auth/login             — password sign-in (returns tokens, or an MFA challenge)
POST /auth/refresh           — new tokens from a refresh token
POST /auth/logout            — sign out of every session
GET  /auth/me                — the signed-in user
POST /auth/change-password   — change your own (local) password
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from src.contracts.schemas.requests.identity.auth_requests import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
)
from src.contracts.schemas.responses.common import (
    CONFLICT_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
    APIResponse,
    ok,
)
from src.contracts.schemas.responses.identity.auth_responses import (
    LoginResultResponse,
    TokenPairResponse,
)
from src.contracts.schemas.responses.identity.user_responses import UserResponse
from src.core.permissions import PROFILE_SELF
from src.dependencies.auth import ActorDep, CurrentUserDep, client_ip, require_permission
from src.dependencies.identity import AuthServiceDep
from src.routers.v1.identity.mappers import login_response, token_response, user_response

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=APIResponse[LoginResultResponse],
    summary="Sign in with username and password",
    responses={**UNAUTHORIZED_RESPONSE, **VALIDATION_ERROR_RESPONSE},
)
async def login(
    request: LoginRequest, http_request: Request, service: AuthServiceDep
) -> APIResponse[LoginResultResponse]:
    result = await service.login(
        username=request.username,
        password=request.password,
        source_ip=client_ip(http_request),
    )
    return ok(login_response(result))


@router.post(
    "/refresh",
    response_model=APIResponse[TokenPairResponse],
    summary="Exchange a refresh token for new tokens",
    responses={**UNAUTHORIZED_RESPONSE, **VALIDATION_ERROR_RESPONSE},
)
async def refresh(
    request: RefreshRequest, service: AuthServiceDep
) -> APIResponse[TokenPairResponse]:
    return ok(token_response(await service.refresh(request.refresh_token)))


@router.post(
    "/logout",
    response_model=APIResponse[None],
    dependencies=[Depends(require_permission(PROFILE_SELF))],
    summary="Sign out of every session",
    responses={**UNAUTHORIZED_RESPONSE},
)
async def logout(service: AuthServiceDep, actor: ActorDep) -> APIResponse[None]:
    await service.logout_everywhere(actor)
    return ok(None, "Signed out of all sessions")


@router.get(
    "/me",
    response_model=APIResponse[UserResponse],
    dependencies=[Depends(require_permission(PROFILE_SELF))],
    summary="The signed-in user",
    responses={**UNAUTHORIZED_RESPONSE},
)
async def me(user: CurrentUserDep) -> APIResponse[UserResponse]:
    return ok(user_response(user))


@router.post(
    "/change-password",
    response_model=APIResponse[TokenPairResponse],
    dependencies=[Depends(require_permission(PROFILE_SELF))],
    summary="Change your own password",
    responses={**UNAUTHORIZED_RESPONSE, **CONFLICT_RESPONSE, **VALIDATION_ERROR_RESPONSE},
)
async def change_password(
    request: ChangePasswordRequest, service: AuthServiceDep, actor: ActorDep
) -> APIResponse[TokenPairResponse]:
    tokens = await service.change_password(
        actor, current=request.current_password, new=request.new_password
    )
    return ok(token_response(tokens), "Password changed; other sessions were signed out")
