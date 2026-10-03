"""Application errors, rendered as ``{success, status_code, error: {code, message, details}}``."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class AccountLockedError(AppError):
    status_code = 423
    code = "account_locked"


class VaultError(AppError):
    """The vault could not decrypt a secret: wrong or missing key, or tampered data."""

    status_code = 500
    code = "vault_error"


class MfaEnrollmentRequired(AppError):
    """The user's role requires MFA and they have not set it up yet."""

    status_code = 403
    code = "mfa_enrollment_required"
