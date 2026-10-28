"""Queued credential rotations (schema groundwork; no engine yet)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import TZ, Base, utcnow
from src.models.inventory.account import Account


class RotationJob(Base):
    __tablename__ = "rotation_jobs"
    __table_args__ = {"schema": "access"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory.accounts.id", ondelete="CASCADE")
    )
    reason: Mapped[str] = mapped_column(String(20))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam.users.id")
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    not_before: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    claimed_by: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(TZ)
    finished_at: Mapped[datetime | None] = mapped_column(TZ)
    from_version: Mapped[int | None] = mapped_column(Integer)
    candidate_version: Mapped[int | None] = mapped_column(Integer)
    driver: Mapped[str | None] = mapped_column(String(40))
    detail: Mapped[str | None] = mapped_column(Text)
    transcript: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam.users.id")
    )
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)

    account: Mapped[Account] = relationship(lazy="joined", innerjoin=True)
