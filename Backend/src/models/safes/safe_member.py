"""A safe member: a user, directory group or role, and its permissions on the safe."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import TZ, Base, utcnow


class SafeMember(Base):
    __tablename__ = "safe_members"
    __table_args__ = {"schema": "inventory"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    safe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory.safes.id", ondelete="CASCADE")
    )
    principal_type: Mapped[str] = mapped_column(String(10))
    principal_key: Mapped[str] = mapped_column(Text)
    permissions: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZ, default=utcnow, onupdate=utcnow)
