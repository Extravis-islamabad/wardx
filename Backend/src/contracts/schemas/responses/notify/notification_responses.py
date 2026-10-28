"""Notification response shapes."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str | None
    object_type: str | None
    object_id: uuid.UUID | None
    created_at: datetime
    read_at: datetime | None


class UnreadCountResponse(BaseModel):
    unread: int
