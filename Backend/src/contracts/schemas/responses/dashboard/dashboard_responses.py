"""Dashboard response shapes."""

from __future__ import annotations

from pydantic import BaseModel


class DashboardSummaryResponse(BaseModel):
    targets: int
    accounts: int
    accounts_without_secret: int
    active_checkouts: int
    pending_requests: int
    my_active_checkouts: int
    my_open_requests: int
