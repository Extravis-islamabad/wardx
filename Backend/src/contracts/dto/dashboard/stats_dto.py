"""Per-page KPI counts (GET /<resource>/stats). Each is counted in the database over
exactly the rows the matching list endpoint would show the same actor."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AccountStatsDTO:
    total: int
    in_use: int
    requires_approval: int
    exclusive: int
    without_secret: int
    out_of_sync: int
    at_risk: int


@dataclass(frozen=True)
class TargetStatsDTO:
    total: int
    active: int
    inactive: int
    platforms: int
    host_key_unpinned: int
    key_changed: int


@dataclass(frozen=True)
class SafeStatsDTO:
    total: int
    accounts: int
    memberships: int
    app_fetch_allowed: int
    approval_required: int
    # Health is computed for safes.manage holders only; None for everyone else.
    break_glass_only: int | None = None
    unreachable: int | None = None


@dataclass(frozen=True)
class UserStatsDTO:
    total: int
    active: int
    disabled: int
    admins: int
    approvers: int
    directory: int
    mfa_enabled: int
    admins_without_mfa: int
    locked: int


@dataclass(frozen=True)
class AppStatsDTO:
    total: int
    enabled: int
    disabled: int
    active_secrets: int
    secrets_expiring: int
    enabled_unusable: int


@dataclass(frozen=True)
class CheckoutStatsDTO:
    total: int
    active: int
    returned: int
    expired: int
    revoked: int
    mine_active: int


@dataclass(frozen=True)
class RequestStatsDTO:
    total: int
    pending: int
    approved: int
    used: int
    denied: int
    expired: int
    cancelled: int
    awaiting_me: int


@dataclass(frozen=True)
class SessionStatsDTO:
    total: int
    active: int
    closed: int
    terminated: int
    failed: int
    mine: int


@dataclass(frozen=True)
class RotationStatsDTO:
    total: int
    # Every job status present, with its count; absent statuses are zero.
    by_status: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditStatsDTO:
    total: int
    last_24h: int
    last_7d: int
    logins_24h: int
    reveals_24h: int
    emergency_reveals_7d: int
    blocked_commands_7d: int
