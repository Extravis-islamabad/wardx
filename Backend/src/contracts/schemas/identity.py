"""Auth and user schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.core.enums import Role

PASSWORD_MIN = 12


def _check_password(value: str) -> str:
    if len(value) < PASSWORD_MIN:
        raise ValueError(f"must be at least {PASSWORD_MIN} characters")
    classes = sum(
        [
            any(c.islower() for c in value),
            any(c.isupper() for c in value),
            any(c.isdigit() for c in value),
            any(not c.isalnum() for c in value),
        ]
    )
    if classes < 3:
        raise ValueError("must mix at least three of: lower case, upper case, digits, symbols")
    return value


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=1024)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginResult(BaseModel):
    """Either tokens, or ``mfa_required`` with a short-lived ``mfa_token`` for /auth/mfa/verify."""

    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int | None = None
    mfa_required: bool = False
    mfa_token: str | None = None
    # Signed in, but the role requires MFA: only enrolment is allowed until it is on.
    mfa_enrollment_required: bool = False


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    code: str = Field(min_length=6, max_length=20)


class MfaCode(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class MfaSetup(BaseModel):
    secret: str
    otpauth_uri: str


class MfaRecoveryCodes(BaseModel):
    recovery_codes: list[str]
    # Fresh tokens: turning MFA on signs out sessions that never proved it.
    tokens: TokenPair | None = None


class MfaStatusOut(BaseModel):
    enabled: bool
    pending: bool
    required: bool
    recovery_codes_left: int


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(max_length=1024)

    _strength = field_validator("new_password")(_check_password)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=150, pattern=r"^[A-Za-z0-9._@-]+$")
    password: str = Field(max_length=1024)
    email: EmailStr | None = None
    full_name: str | None = Field(None, max_length=255)
    role: Role = Role.USER

    _strength = field_validator("password")(_check_password)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(None, max_length=255)
    role: Role | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    new_password: str = Field(max_length=1024)

    _strength = field_validator("new_password")(_check_password)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str | None
    full_name: str | None
    role: Role
    is_active: bool
    locked_until: datetime | None
    last_login_at: datetime | None
    auth_source: str = "local"
    created_at: datetime
