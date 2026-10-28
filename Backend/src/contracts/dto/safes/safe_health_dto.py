"""Safe health and dashboard-attention DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

HEALTHY = "healthy"
BREAK_GLASS_ONLY = "break_glass_only"  # warning
UNREACHABLE = "unreachable"  # critical
SEVERITY = {HEALTHY: None, BREAK_GLASS_ONLY: "warning", UNREACHABLE: "critical"}
# Fewer eligible break-glass holders than this is a single point of failure.
MIN_BREAK_GLASS_HOLDERS = 2


@dataclass(frozen=True)
class SafeMembershipSummaryDTO:
    """Who can reach an active safe, by kind of member."""

    safe_id: uuid.UUID
    name: str
    user_members: int  # direct members who are active users
    role_members: int  # role members whose role has at least one active user
    group_members: int
    # The same counts for local users only: what still signs in with the directory down.
    local_user_members: int
    local_role_members: int


@dataclass(frozen=True)
class SafeHealthDTO:
    safe_id: uuid.UUID
    name: str
    state: str
    user_members: int
    role_members: int
    group_members: int

    @property
    def severity(self) -> str | None:
        return SEVERITY[self.state]


@dataclass(frozen=True)
class BreakGlassCoverageDTO:
    eligible_holders: int
    holders: int  # including ineligible ones (MFA off, disabled, ...)

    @property
    def warning(self) -> bool:
        return self.eligible_holders < MIN_BREAK_GLASS_HOLDERS


@dataclass(frozen=True)
class DirectoryStatusDTO:
    enabled: bool
    reachable: bool | None
    checked_at: datetime | None
    error: str | None
    # Only while unreachable: active safes nobody can reach once groups count as none.
    affected_safes: list[SafeHealthDTO] = field(default_factory=list)

    @property
    def unreachable(self) -> bool:
        return self.enabled and self.reachable is False


@dataclass(frozen=True)
class AttentionDTO:
    directory: DirectoryStatusDTO
    break_glass: BreakGlassCoverageDTO
    safes: list[SafeHealthDTO]
