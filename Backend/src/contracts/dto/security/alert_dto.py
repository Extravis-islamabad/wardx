"""Security alert DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class AlertDTO:
    id: uuid.UUID
    created_at: datetime
    severity: str
    kind: str
    message: str
    actor_id: uuid.UUID | None
    actor_name: str | None
    object_type: str | None
    object_id: uuid.UUID | None
    details: dict[str, Any]
    acknowledged_by: uuid.UUID | None
    acknowledged_at: datetime | None


@dataclass(frozen=True)
class AlertFilterDTO:
    severity: str | None = None
    # True: only acknowledged; False: only open; None: both.
    acknowledged: bool | None = None
