"""One person's decision on a request, at the level it was made."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import TZ, Base, utcnow
from src.models.identity.user import User


class RequestDecision(Base):
    __tablename__ = "request_decisions"
    __table_args__ = {"schema": "access"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("access.requests.id", ondelete="CASCADE")
    )
    level: Mapped[int] = mapped_column(Integer)
    approver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("iam.users.id"))
    approve: Mapped[bool] = mapped_column(Boolean)
    note: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)

    approver: Mapped[User] = relationship(lazy="joined", innerjoin=True)
