"""Envelope-encrypted secret versions (see src/vault/envelope.py)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import TZ, Base, utcnow


class Secret(Base):
    __tablename__ = "secrets"
    __table_args__ = {"schema": "vault"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_type: Mapped[str] = mapped_column(String(30))
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary)
    dek_nonce: Mapped[bytes] = mapped_column(LargeBinary)
    kek_id: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # current | previous | candidate | abandoned: a label only; accounts.secret_version
    # is the source of truth for the current version.
    status: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
