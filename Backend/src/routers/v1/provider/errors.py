"""OpenAPI documentation of the credential provider's error codes, one example per code."""

from __future__ import annotations

from typing import Any

from src.contracts.schemas.responses.common import ErrorResponse
from src.errors.exceptions import AppError
from src.services.provider.provider_errors import (
    ApprovalRequired,
    CredentialAmbiguous,
    CredentialNotFound,
    InvalidClient,
    InvalidToken,
    IpNotAllowed,
    NoSecret,
    RateLimited,
    RotationNeedsAttention,
    VerifyUntrustworthy,
)


def provider_errors(*errors: type[AppError]) -> dict[int | str, Any]:
    """``responses=`` entries: per status, an example of every listed error code."""
    out: dict[int | str, Any] = {}
    for error in errors:
        entry = out.setdefault(
            error.status_code,
            {
                "description": f"HTTP {error.status_code}",
                "model": ErrorResponse,
                "content": {"application/json": {"examples": {}}},
            },
        )
        entry["content"]["application/json"]["examples"][error.code] = {
            "value": {
                "success": False,
                "status_code": error.status_code,
                "error": {
                    "code": error.code,
                    "message": error.__doc__ or error.code,
                    "details": {},
                },
            }
        }
    return out


TOKEN_ERRORS = provider_errors(InvalidClient, IpNotAllowed, RateLimited)
FETCH_ERRORS = provider_errors(
    InvalidToken,
    IpNotAllowed,
    CredentialNotFound,
    CredentialAmbiguous,
    ApprovalRequired,
    VerifyUntrustworthy,
    RotationNeedsAttention,
    NoSecret,
    RateLimited,
)
