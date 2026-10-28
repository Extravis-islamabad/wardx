"""Per-tenant keys, stored only wrapped by the key provider."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import TZ, Base, utcnow


class TenantKey(Base):
    __tablename__ = "tenant_keys"
    __table_args__ = {"schema": "keystore"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    purpose: Mapped[str] = mapped_column(String(16))
    version: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(12), default="active")
    kek_id: Mapped[str] = mapped_column(Text)
    wrapped_key: Mapped[bytes | None] = mapped_column(LargeBinary)
    wrap_nonce: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    retired_at: Mapped[datetime | None] = mapped_column(TZ)
    destroyed_at: Mapped[datetime | None] = mapped_column(TZ)
