"""In-app notifications, per user, with read and unread state."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import TZ, Base, utcnow


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = {"schema": "notify"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("iam.users.id"))
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    object_type: Mapped[str | None] = mapped_column(String(40))
    object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(TZ)
