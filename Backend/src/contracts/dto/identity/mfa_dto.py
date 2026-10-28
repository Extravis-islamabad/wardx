"""MFA DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class UserMfaDTO:
    user_id: uuid.UUID
    secret_version: int
    enabled: bool
    last_used_step: int | None
    enrolled_at: datetime | None


@dataclass(frozen=True)
class MfaStatusDTO:
    enabled: bool
    pending: bool
    required: bool
    recovery_codes_left: int
