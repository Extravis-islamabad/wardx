"""Common response envelopes and the reusable error responses for OpenAPI docs."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Standard API response wrapper."""

    success: bool = True
    data: T
    message: str | None = None


class PaginatedAPIResponse(BaseModel, Generic[T]):
    """A page of a list, with the total across all pages."""

    success: bool = True
    data: list[T]
    total: int
    page: int
    page_size: int


def ok(data: T, message: str | None = None) -> APIResponse[T]:
    return APIResponse[T](data=data, message=message)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Every error: ``{success, status_code, error: {code, message, details}}``."""

    success: bool = False
    status_code: int
    error: ErrorDetail


def _error(status: int, description: str, code: str, message: str) -> dict[int | str, Any]:
    return {
        status: {
            "description": description,
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "status_code": status,
                        "error": {"code": code, "message": message, "details": {}},
                    }
                }
            },
        }
    }


UNAUTHORIZED_RESPONSE = _error(401, "Missing or invalid token", "unauthorized", "Invalid token")
FORBIDDEN_RESPONSE = _error(
    403, "Insufficient permissions", "forbidden", "Missing required permission: inventory.manage"
)
NOT_FOUND_RESPONSE = _error(404, "Resource not found", "not_found", "Account not found")
CONFLICT_RESPONSE = _error(
    409, "State conflict", "conflict", "Account is checked out by someone else"
)
VALIDATION_ERROR_RESPONSE = _error(
    422, "Validation error", "validation_error", "Request validation failed"
)
