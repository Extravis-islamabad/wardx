"""Rotation response shapes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RotationStepResponse(BaseModel):
    step: str
    outcome: str
    secret_version: int | None
    detail: str | None
    # Device conversation with every secret replaced by ****.
    transcript: str | None
    started_at: datetime
    finished_at: datetime


class RotationJobResponse(BaseModel):
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
    steps: list[RotationStepResponse] = []


class SafeRotationPolicyResponse(BaseModel):
    safe_id: uuid.UUID
    rotate_after_use: bool
    rotation_interval_days: int | None
    verify_interval_hours: int
    auto_reconcile: bool
    maintenance_window: dict[str, Any] | None
    max_release_wait_minutes: int


class AccountRotationResponse(BaseModel):
    account_id: uuid.UUID
    username: str
    target_name: str
    platform: str
    protocol: str
    sync_status: str
    rotation_status: str
    last_rotated_at: datetime | None
    last_rotation_status: str | None
    last_verified_at: datetime | None
    last_verify_method: str | None
    risk_flags: list[str]
    risk_accepted_by: uuid.UUID | None = None
    risk_accepted_at: datetime | None = None
    risk_accepted_reason: str | None = None
    reconcile_account_id: uuid.UUID | None
    rotation_allowed: bool
    rotation_enabled: bool
    host_key_pinned: bool
    non_rotatable_reason: str | None
    effective_policy: dict[str, Any] | None
    policy_error: str | None
    effective_interval_days: int | None
    effective_rotate_after_use: bool
    safe_policy: SafeRotationPolicyResponse
    open_job: RotationJobResponse | None
    jobs: list[RotationJobResponse]


class RotationAccountBriefResponse(BaseModel):
    id: uuid.UUID
    username: str
    safe_id: uuid.UUID
    sync_status: str
    risk_flags: list[str]
    last_verified_at: datetime | None
    # confirmed_untrustworthy: who accepted the risk, when and why.
    risk_accepted_by: uuid.UUID | None = None
    risk_accepted_by_name: str | None = None
    risk_accepted_at: datetime | None = None
    risk_accepted_reason: str | None = None


class RotationAttentionResponse(BaseModel):
    needs_attention: list[RotationJobResponse]
    out_of_sync: list[RotationAccountBriefResponse]
    verify_untrustworthy: list[RotationAccountBriefResponse]
    confirmed_untrustworthy: list[RotationAccountBriefResponse]
    empty_password: list[RotationAccountBriefResponse]
    release_overdue: list[RotationJobResponse]
