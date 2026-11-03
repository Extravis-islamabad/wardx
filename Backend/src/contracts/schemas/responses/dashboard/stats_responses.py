"""Per-page KPI response shapes (GET /<resource>/stats); fields mirror the stats DTOs."""

from __future__ import annotations

from pydantic import BaseModel


class AccountStatsResponse(BaseModel):
    total: int
    in_use: int
    requires_approval: int
    exclusive: int
    without_secret: int
    out_of_sync: int
    at_risk: int


class TargetStatsResponse(BaseModel):
    total: int
    active: int
    inactive: int
    platforms: int
    host_key_unpinned: int
    key_changed: int


class SafeStatsResponse(BaseModel):
    total: int
    accounts: int
    memberships: int
    app_fetch_allowed: int
    approval_required: int
    break_glass_only: int | None = None
    unreachable: int | None = None


class UserStatsResponse(BaseModel):
    total: int
    active: int
    disabled: int
    admins: int
    approvers: int
    directory: int
    mfa_enabled: int
    admins_without_mfa: int
    locked: int


class AppStatsResponse(BaseModel):
    total: int
    enabled: int
    disabled: int
    active_secrets: int
    secrets_expiring: int
    enabled_unusable: int


class CheckoutStatsResponse(BaseModel):
    total: int
    active: int
    returned: int
    expired: int
    revoked: int
    mine_active: int


class RequestStatsResponse(BaseModel):
    total: int
    pending: int
    approved: int
    used: int
    denied: int
    expired: int
    cancelled: int
    awaiting_me: int


class SessionStatsResponse(BaseModel):
    total: int
    active: int
    closed: int
    terminated: int
    failed: int
    mine: int


class RotationStatsResponse(BaseModel):
    total: int
    by_status: dict[str, int]


class AuditStatsResponse(BaseModel):
    total: int
    last_24h: int
    last_7d: int
    logins_24h: int
    reveals_24h: int
    emergency_reveals_7d: int
    blocked_commands_7d: int
