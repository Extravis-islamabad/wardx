"""Safes: the containers privileged accounts live in, and who may do what with them."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import TZ, Base, utcnow


class Safe(Base):
    __tablename__ = "safes"
    __table_args__ = {"schema": "inventory"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Approval policy (section (b)); levels live in safe_approval_levels.
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    ticket_mode: Mapped[str] = mapped_column(String(10), default="off")
    ticket_pattern: Mapped[str | None] = mapped_column(String(200))
    approval_window_minutes: Mapped[int] = mapped_column(Integer, default=120)
    approval_multi_use: Mapped[bool] = mapped_column(Boolean, default=False)
    level_timeout_hours: Mapped[int] = mapped_column(Integer, default=24)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZ, default=utcnow, onupdate=utcnow)
