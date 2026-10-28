"""User DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class UserDTO:
    id: uuid.UUID
    username: str
    email: str | None
    full_name: str | None
    # Argon2 hash for local users; a never-verifying marker for directory users.
    password_hash: str
    role: str
    is_active: bool
    token_version: int
    failed_logins: int
    locked_until: datetime | None
    last_login_at: datetime | None
    auth_source: str
    external_id: str | None
    directory_synced_at: datetime | None
    disabled_reason: str | None
    created_at: datetime


@dataclass(frozen=True)
class UserFilterDTO:
    search: str | None = None
