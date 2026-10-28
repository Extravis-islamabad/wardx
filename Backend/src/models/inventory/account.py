"""Privileged accounts on targets, with their check-out and rotation policy."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import TZ, Base, utcnow
from src.models.inventory.target import Target


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = {"schema": "inventory"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory.targets.id", ondelete="CASCADE")
    )
    username: Mapped[str] = mapped_column(String(255))
    secret_type: Mapped[str] = mapped_column(String(20), default="password")
    description: Mapped[str | None] = mapped_column(Text)
    secret_version: Mapped[int] = mapped_column(Integer, default=0)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    exclusive_checkout: Mapped[bool] = mapped_column(Boolean, default=True)
    max_checkout_minutes: Mapped[int] = mapped_column(Integer, default=60)
    secret_updated_at: Mapped[datetime | None] = mapped_column(TZ)
    rotation_interval_days: Mapped[int | None] = mapped_column(Integer)
    rotate_after_checkin: Mapped[bool] = mapped_column(Boolean, default=False)
    password_length: Mapped[int] = mapped_column(Integer, default=24)
    last_rotated_at: Mapped[datetime | None] = mapped_column(TZ)
    last_rotation_status: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZ, default=utcnow, onupdate=utcnow)

    target: Mapped[Target] = relationship(lazy="joined", innerjoin=True)
