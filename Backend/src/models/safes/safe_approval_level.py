"""One ordered approval level of a safe's policy."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class SafeApprovalLevel(Base):
    __tablename__ = "safe_approval_levels"
    __table_args__ = {"schema": "inventory"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    safe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory.safes.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    required_approvals: Mapped[int] = mapped_column(Integer, default=1)
    approver_type: Mapped[str] = mapped_column(String(20))
    approver_key: Mapped[str | None] = mapped_column(Text)
