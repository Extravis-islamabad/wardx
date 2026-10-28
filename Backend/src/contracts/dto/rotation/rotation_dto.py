"""Rotation DTOs: jobs, steps, the engine's working context, safe rotation policy."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Job states (ROTATION.md section 5).
PENDING = "pending"
WAITING_RELEASE = "waiting_release"
RUNNING = "running"
CANDIDATE_STORED = "candidate_stored"
DEVICE_CHANGED = "device_changed"
PERSISTED = "persisted"
SUCCEEDED = "succeeded"
# The device holds the new password (it is current) but the verify did not prove it.
CHANGED_UNVERIFIED = "changed_unverified"
FAILED = "failed"
NEEDS_ATTENTION = "needs_attention"
RESOLVED = "resolved"
CANCELLED = "cancelled"

OPEN_STATES = frozenset(
    {
        PENDING,
        WAITING_RELEASE,
        RUNNING,
        CANDIDATE_STORED,
        DEVICE_CHANGED,
        PERSISTED,
        NEEDS_ATTENTION,
    }
)
# A worker may pick these up (a crashed worker's job is resumed from its state).
CLAIMABLE_STATES = frozenset({PENDING, RUNNING, CANDIDATE_STORED, DEVICE_CHANGED, PERSISTED})
# While a job is in one of these, normal check-outs and gateway sessions are refused.
BLOCKING_STATES = frozenset(
    {WAITING_RELEASE, RUNNING, CANDIDATE_STORED, DEVICE_CHANGED, PERSISTED, NEEDS_ATTENTION}
)

# Reasons (triggers).
MANUAL = "manual"
SCHEDULE = "schedule"
AFTER_USE = "after_use"
RECONCILE = "reconcile"
VERIFY = "verify"
COMPROMISE = "compromise"

# Account sync states.
UNKNOWN = "unknown"
IN_SYNC = "in_sync"
OUT_OF_SYNC = "out_of_sync"
UNREACHABLE = "unreachable"
UNVERIFIED = "unverified"
VERIFY_UNTRUSTWORTHY = "verify_untrustworthy"
# An administrator confirmed an untrustworthy verify (risk accepted): normal access is
# allowed again, but the account stays listed until a later clean verify.
CONFIRMED_UNTRUSTWORTHY = "confirmed_untrustworthy"

# Negative-check results of a verify.
VERIFIED = "verified"
UNTRUSTWORTHY = "untrustworthy"
INCONCLUSIVE = "inconclusive"

HIGH_RISK_EMPTY_PASSWORD = "high_risk_empty_password"


@dataclass(frozen=True)
class RotationStepDTO:
    id: int
    step: str
    outcome: str
    secret_version: int | None
    detail: str | None
    transcript: str | None
    started_at: datetime
    finished_at: datetime


@dataclass(frozen=True)
class RotationJobDTO:
    id: uuid.UUID
    account_id: uuid.UUID
    account_username: str
    target_id: uuid.UUID
    target_name: str
    safe_id: uuid.UUID
    reason: str
    status: str
    requested_by: uuid.UUID | None
    note: str | None
    dry_run: bool
    not_before: datetime
    attempts: int
    lease_until: datetime | None
    change_sent_at: datetime | None
    waiting_since: datetime | None
    release_alerted_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    from_version: int | None
    candidate_version: int | None
    secret_versions_touched: list[int]
    driver: str | None
    detail: str | None
    verify_result: str | None
    resolution: str | None
    resolution_note: str | None
    resolved_by: uuid.UUID | None
    resolved_at: datetime | None
    created_at: datetime
    steps: list[RotationStepDTO] = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATES


@dataclass(frozen=True)
class RotationFilterDTO:
    status: str | None = None
    reason: str | None = None
    account_id: uuid.UUID | None = None
    # Only jobs of accounts in these safes; None = no restriction.
    safe_ids: frozenset[uuid.UUID] | None = None


@dataclass(frozen=True)
class SafeRotationPolicyDTO:
    safe_id: uuid.UUID
    rotate_after_use: bool = False
    rotation_interval_days: int | None = None
    verify_interval_hours: int = 24
    auto_reconcile: bool = False
    maintenance_window: dict[str, Any] | None = None
    max_release_wait_minutes: int = 240

    def audit_view(self) -> dict[str, Any]:
        return {
            "rotate_after_use": self.rotate_after_use,
            "rotation_interval_days": self.rotation_interval_days,
            "verify_interval_hours": self.verify_interval_hours,
            "auto_reconcile": self.auto_reconcile,
            "maintenance_window": self.maintenance_window,
            "max_release_wait_minutes": self.max_release_wait_minutes,
        }


@dataclass(frozen=True)
class RotationTargetDTO:
    id: uuid.UUID
    name: str
    address: str
    port: int
    platform: str
    protocol: str
    is_active: bool
    rotation_allowed: bool
    policy_overrides: dict[str, Any]
    ssh_host_key: str | None


@dataclass(frozen=True)
class RotationAccountDTO:
    """What the engine needs to know about an account (never its secret)."""

    id: uuid.UUID
    username: str
    secret_type: str
    safe_id: uuid.UUID
    secret_version: int
    password_length: int
    rotation_interval_days: int | None
    rotate_after_use: bool
    reconcile_account_id: uuid.UUID | None
    sync_status: str
    rotation_status: str
    last_rotated_at: datetime | None
    last_verified_at: datetime | None
    last_verify_method: str | None
    last_rotation_status: str | None
    unreachable_count: int
    risk_flags: list[str]
    created_at: datetime
    risk_accepted_by: uuid.UUID | None = None
    risk_accepted_at: datetime | None = None
    risk_accepted_reason: str | None = None
    risk_accepted_by_name: str | None = None


@dataclass(frozen=True)
class RotationContextDTO:
    job: RotationJobDTO
    account: RotationAccountDTO
    target: RotationTargetDTO
    policy: SafeRotationPolicyDTO
    # The reconcile account (its own row: version, username), when one is linked.
    reconcile: RotationAccountDTO | None


@dataclass(frozen=True)
class RotationAttentionDTO:
    needs_attention: list[RotationJobDTO]
    out_of_sync: list[RotationAccountDTO]
    untrustworthy: list[RotationAccountDTO]
    confirmed_untrustworthy: list[RotationAccountDTO]
    empty_password: list[RotationAccountDTO]
    release_overdue: list[RotationJobDTO]
