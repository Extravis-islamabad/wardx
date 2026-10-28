"""Privileged accounts on targets, with their check-out and rotation policy."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import TZ, Base, utcnow
from src.models.inventory.target import Target
from src.models.safes.safe import Safe


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = {"schema": "inventory"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory.targets.id", ondelete="CASCADE")
    )
    safe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory.safes.id", ondelete="RESTRICT")
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
    rotate_after_use: Mapped[bool] = mapped_column(Boolean, default=False)
    password_length: Mapped[int] = mapped_column(Integer, default=24)
    last_rotated_at: Mapped[datetime | None] = mapped_column(TZ)
    last_rotation_status: Mapped[str | None] = mapped_column(String(24))
    reconcile_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory.accounts.id", ondelete="SET NULL")
    )
    sync_status: Mapped[str] = mapped_column(String(24), default="unknown")
    last_verified_at: Mapped[datetime | None] = mapped_column(TZ)
    last_verify_method: Mapped[str | None] = mapped_column(String(12))
    last_verify_attempt_at: Mapped[datetime | None] = mapped_column(TZ)
    unreachable_count: Mapped[int] = mapped_column(Integer, default=0)
    rotation_status: Mapped[str] = mapped_column(String(20), default="idle")
    risk_flags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    risk_checked_version: Mapped[int] = mapped_column(Integer, default=0)
    risk_accepted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    risk_accepted_at: Mapped[datetime | None] = mapped_column(TZ)
    risk_accepted_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZ, default=utcnow, onupdate=utcnow)

    target: Mapped[Target] = relationship(lazy="joined", innerjoin=True)
    safe: Mapped[Safe] = relationship(lazy="joined", innerjoin=True)
