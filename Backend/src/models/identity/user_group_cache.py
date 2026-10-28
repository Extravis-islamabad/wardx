"""A directory user's groups (normalised DNs) as of ``fetched_at``."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import TZ, Base


class UserGroupCache(Base):
    __tablename__ = "user_group_cache"
    __table_args__ = {"schema": "iam"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam.users.id", ondelete="CASCADE"), primary_key=True
    )
    groups: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    fetched_at: Mapped[datetime] = mapped_column(TZ)
