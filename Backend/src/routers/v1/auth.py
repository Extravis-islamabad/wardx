from __future__ import annotations

from fastapi import APIRouter, Request

from src.contracts.schemas.common import APIResponse, ok
from src.contracts.schemas.identity import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    TokenPair,
    UserOut,
)
from src.core.config import get_settings
from src.dependencies.auth import ActorDep, CurrentUser, SessionDep, client_ip
from src.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=APIResponse[TokenPair])
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
