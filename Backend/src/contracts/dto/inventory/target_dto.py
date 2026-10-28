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
    ssh_host_key_fingerprint: str | None
    ssh_host_key_learned_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class TargetFilterDTO:
    search: str | None = None
    platform: str | None = None
