"""Notification DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NotificationDTO:
    id: uuid.UUID
    user_id: uuid.UUID
    kind: str
    title: str
    body: str | None
    object_type: str | None
    object_id: uuid.UUID | None
    created_at: datetime
    read_at: datetime | None
