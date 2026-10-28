"""Token DTOs issued at sign-in."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenPairDTO:
    access_token: str
    refresh_token: str
    expires_in: int


@dataclass(frozen=True)
class LoginResultDTO:
    """Either ``tokens``, or ``mfa_required`` with a short-lived ``mfa_token``."""

    tokens: TokenPairDTO | None = None
    mfa_required: bool = False
    mfa_token: str | None = None
    # Signed in, but the role requires MFA: only enrolment is allowed until it is on.
    mfa_enrollment_required: bool = False
