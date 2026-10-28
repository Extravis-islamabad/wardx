"""Transitional re-exports: import from requests/common and responses/common instead."""

from src.contracts.schemas.requests.common import PageParams
from src.contracts.schemas.responses.common import APIResponse, PaginatedAPIResponse, ok

__all__ = ["APIResponse", "PageParams", "PaginatedAPIResponse", "ok"]
