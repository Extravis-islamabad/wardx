"""The credential provider's distinct error codes (docs/phase1/CREDENTIAL_PROVIDER.md §5).

Every refusal uses the standard envelope. ``PROVIDER_ERRORS`` lists them all: the MonetX
contract (docs/integrations/monetx-credential-provider-api.md) is checked against it.
"""

from __future__ import annotations

from typing import Any

from src.errors.exceptions import AppError


class InvalidToken(AppError):
    """Missing, malformed, expired or revoked app token, or the app is disabled."""

    status_code = 401
    code = "invalid_token"


class InvalidClient(AppError):
    """Wrong client_id or client_secret on the token route (never says which)."""

    status_code = 401
    code = "invalid_client"


class IpNotAllowed(AppError):
    status_code = 403
    code = "ip_not_allowed"


class CredentialNotFound(AppError):
    """No fetchable account matches, or the app has no ``fetch`` there: not distinguished."""

    status_code = 404
    code = "credential_not_found"


class CredentialAmbiguous(AppError):
    status_code = 409
    code = "credential_ambiguous"


class CredentialUnavailable(AppError):
    """The account exists and the app may fetch it, but WardX will not serve it now."""

    status_code = 409
    code = "credential_unavailable"


class ApprovalRequired(CredentialUnavailable):
    code = "credential_unavailable.approval_required"


class VerifyUntrustworthy(CredentialUnavailable):
    code = "credential_unavailable.verify_untrustworthy"


class RotationNeedsAttention(CredentialUnavailable):
    code = "credential_unavailable.rotation_needs_attention"


class NoSecret(CredentialUnavailable):
    code = "credential_unavailable.no_secret"


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"

    def __init__(
        self, message: str, retry_after: int, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message, {**(details or {}), "retry_after": retry_after})
        self.headers = {"Retry-After": str(max(1, retry_after))}


PROVIDER_ERRORS: tuple[type[AppError], ...] = (
    InvalidToken,
    InvalidClient,
    IpNotAllowed,
    CredentialNotFound,
    CredentialAmbiguous,
    ApprovalRequired,
    VerifyUntrustworthy,
    RotationNeedsAttention,
    NoSecret,
    RateLimited,
)
