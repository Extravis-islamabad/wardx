"""Response mappings shared by the identity routers."""

from __future__ import annotations

from src.contracts.dto.identity.token_dto import LoginResultDTO, TokenPairDTO
from src.contracts.dto.identity.user_dto import UserDTO
from src.contracts.schemas.responses.identity.auth_responses import (
    LoginResultResponse,
    TokenPairResponse,
)
from src.contracts.schemas.responses.identity.user_responses import UserResponse
from src.core.enums import Role


def user_response(dto: UserDTO) -> UserResponse:
    return UserResponse(
        id=dto.id,
        username=dto.username,
        email=dto.email,
        full_name=dto.full_name,
        role=Role(dto.role),
        is_active=dto.is_active,
        locked_until=dto.locked_until,
        last_login_at=dto.last_login_at,
        auth_source=dto.auth_source,
        disabled_reason=dto.disabled_reason,
        created_at=dto.created_at,
    )


def token_response(dto: TokenPairDTO) -> TokenPairResponse:
    return TokenPairResponse(
        access_token=dto.access_token, refresh_token=dto.refresh_token, expires_in=dto.expires_in
    )


def login_response(dto: LoginResultDTO) -> LoginResultResponse:
    tokens = dto.tokens
    return LoginResultResponse(
        access_token=tokens.access_token if tokens else None,
        refresh_token=tokens.refresh_token if tokens else None,
        expires_in=tokens.expires_in if tokens else None,
        mfa_required=dto.mfa_required,
        mfa_token=dto.mfa_token,
        mfa_enrollment_required=dto.mfa_enrollment_required,
    )
