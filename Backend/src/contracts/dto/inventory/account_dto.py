"""Privileged account DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TargetBriefDTO:
    id: uuid.UUID
    name: str
    address: str
    platform: str
    protocol: str
    port: int


@dataclass(frozen=True)
class AccountDTO:
    id: uuid.UUID
    target: TargetBriefDTO
    username: str
    secret_type: str
    description: str | None
    secret_version: int
    secret_updated_at: datetime | None
    requires_approval: bool
    exclusive_checkout: bool
    max_checkout_minutes: int
    rotation_interval_days: int | None
    rotate_after_checkin: bool
    password_length: int
    last_rotated_at: datetime | None
    last_rotation_status: str | None
    created_at: datetime
    active_checkouts: int = 0

    @property
    def target_id(self) -> uuid.UUID:
        return self.target.id

    @property
    def has_secret(self) -> bool:
        return self.secret_version > 0


@dataclass(frozen=True)
class AccountFilterDTO:
    target_id: uuid.UUID | None = None
    search: str | None = None
