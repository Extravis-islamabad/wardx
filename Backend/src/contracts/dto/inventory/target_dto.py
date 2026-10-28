"""Target DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TargetDTO:
    id: uuid.UUID
    name: str
    address: str
    platform: str
    protocol: str
    port: int
    description: str | None
    tags: list[str]
    external_ref: str | None
    is_active: bool
    # The pinned SSH host public key the gateway verifies the device against.
    ssh_host_key: str | None
    ssh_host_key_fingerprint: str | None
    ssh_host_key_learned_at: datetime | None
    created_at: datetime
    updated_at: datetime
    rotation_allowed: bool = False
    policy_overrides: dict | None = None
    # Set when the device presented another key: rotation and verify are blocked until an
    # administrator accepts a key again (ROTATION.md §14, fix 4).
    host_key_mismatch_at: datetime | None = None
    host_key_mismatch_fingerprint: str | None = None


@dataclass(frozen=True)
class TargetFilterDTO:
    search: str | None = None
    platform: str | None = None
