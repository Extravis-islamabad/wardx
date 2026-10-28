"""An application identity's client secret: an argon2id hash and a display prefix only."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import TZ, Base, utcnow


class AppSecret(Base):
    __tablename__ = "app_secrets"
    __table_args__ = {"schema": "iam"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam.apps.id", ondelete="CASCADE")
    )
    slot: Mapped[int] = mapped_column(SmallInteger)
    secret_hash: Mapped[str] = mapped_column(Text)
    prefix: Mapped[str] = mapped_column(String(16))
    expires_at: Mapped[datetime | None] = mapped_column(TZ)
    revoked_at: Mapped[datetime | None] = mapped_column(TZ)
    last_used_at: Mapped[datetime | None] = mapped_column(TZ)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
