"""Time-boxed check-outs of an account by a user."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import TZ, Base, utcnow
from src.models.identity.user import User
from src.models.inventory.account import Account


class Checkout(Base):
    __tablename__ = "checkouts"
    __table_args__ = {"schema": "access"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory.accounts.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("iam.users.id"))
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("access.requests.id")
    )
    reason: Mapped[str] = mapped_column(Text)
    secret_version: Mapped[int] = mapped_column(Integer)
    checked_out_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TZ)
    checked_in_at: Mapped[datetime | None] = mapped_column(TZ)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam.users.id")
    )
    status: Mapped[str] = mapped_column(String(20), default="active")
    # A break-glass reveal (POST /accounts/{id}/emergency-reveal).
    emergency: Mapped[bool] = mapped_column(Boolean, default=False)

    account: Mapped[Account] = relationship(lazy="joined", innerjoin=True)
    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined", innerjoin=True)
