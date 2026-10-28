"""Sign-in and MFA response shapes."""

from __future__ import annotations

from pydantic import BaseModel


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginResultResponse(BaseModel):
    """Either tokens, or ``mfa_required`` with a short-lived ``mfa_token`` for /auth/mfa/verify."""

    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int | None = None
    mfa_required: bool = False
    mfa_token: str | None = None
    # Signed in, but the role requires MFA: only enrolment is allowed until it is on.
    mfa_enrollment_required: bool = False


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class MfaRecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]
    # Fresh tokens: turning MFA on signs out sessions that never proved it.
    tokens: TokenPairResponse | None = None


class MfaStatusResponse(BaseModel):
    enabled: bool
    pending: bool
    required: bool
    recovery_codes_left: int
