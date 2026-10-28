"""Dashboard DTOs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DashboardSummaryDTO:
    targets: int
    accounts: int
    accounts_without_secret: int
    active_checkouts: int
    pending_requests: int
    my_active_checkouts: int
    my_open_requests: int
