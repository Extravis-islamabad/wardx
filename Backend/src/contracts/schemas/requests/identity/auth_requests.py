"""Sign-in, password change and MFA request shapes."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from src.contracts.schemas.requests.identity.user_requests import check_password_strength


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=1024)


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(max_length=1024)

    _strength = field_validator("new_password")(check_password_strength)


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    code: str = Field(min_length=6, max_length=20)


class MfaCode(BaseModel):
    code: str = Field(min_length=6, max_length=20)
