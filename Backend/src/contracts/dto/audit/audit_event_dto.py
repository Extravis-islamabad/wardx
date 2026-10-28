"""Audit trail DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class AuditEventDTO:
    seq: int
    id: uuid.UUID
    occurred_at: datetime
    actor_id: uuid.UUID | None
    actor_name: str | None
    action: str
    object_type: str | None
    object_id: uuid.UUID | None
    outcome: str
    source_ip: str | None
    details: dict[str, Any]
    prev_hash: str
    hash: str
    key_version: int | None = None


@dataclass(frozen=True)
class AuditFilterDTO:
    action: str | None = None
    actor_id: uuid.UUID | None = None
    object_id: uuid.UUID | None = None
    since: datetime | None = None
    until: datetime | None = None
