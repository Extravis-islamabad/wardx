"""Account response shapes."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class TargetBriefResponse(BaseModel):
    id: uuid.UUID
    name: str
    address: str
    platform: str
    protocol: str


class SafeBriefResponse(BaseModel):
    id: uuid.UUID
    name: str


class AccountResponse(BaseModel):
    id: uuid.UUID
    target: TargetBriefResponse
    safe: SafeBriefResponse
    username: str
    secret_type: str
    description: str | None
    has_secret: bool
    secret_version: int
    secret_updated_at: datetime | None
    requires_approval: bool
    exclusive_checkout: bool
    max_checkout_minutes: int
    active_checkouts: int = 0
    created_at: datetime
    # Rotation (docs/phase1/ROTATION.md).
    rotation_interval_days: int | None = None
    rotate_after_use: bool = False
    password_length: int = 24
    reconcile_account_id: uuid.UUID | None = None
    sync_status: str = "unknown"
    last_verified_at: datetime | None = None
    last_verify_method: str | None = None
    last_rotated_at: datetime | None = None
    last_rotation_status: str | None = None
    rotation_status: str = "idle"
    risk_flags: list[str] = []
