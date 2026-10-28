"""Each command typed in a gateway session and the policy verdict."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import TZ, Base


class SessionCommand(Base):
    __tablename__ = "session_commands"
    __table_args__ = {"schema": "access"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("access.sessions.id", ondelete="CASCADE")
    )
    occurred_at: Mapped[datetime] = mapped_column(TZ)
    offset_seconds: Mapped[float] = mapped_column(Float)
    command: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(10))
    rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
