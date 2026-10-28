"""Audit trail response shapes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditEventResponse(BaseModel):
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
    hash: str
    # The safe the event belongs to (None for events before migration 016 and non-safe events).
    safe_id: uuid.UUID | None = None


class ChainVerificationResponse(BaseModel):
    ok: bool
    checked: int
    broken_at_seq: int | None
    reason: str | None
