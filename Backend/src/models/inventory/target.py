"""Devices, hosts, databases and consoles that privileged accounts live on."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import TZ, Base, utcnow


class Target(Base):
    __tablename__ = "targets"
    __table_args__ = {"schema": "inventory"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str] = mapped_column(String(255))
    platform: Mapped[str] = mapped_column(String(40))
    protocol: Mapped[str] = mapped_column(String(10))
    port: Mapped[int] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    external_ref: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    ssh_host_key: Mapped[str | None] = mapped_column(Text)
    ssh_host_key_fingerprint: Mapped[str | None] = mapped_column(String(128))
    ssh_host_key_learned_at: Mapped[datetime | None] = mapped_column(TZ)
    # Rotation (docs/phase1/ROTATION.md): the per-target switch, off by default, and
    # device-specific policy caps.
    rotation_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    policy_overrides: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZ, default=utcnow, onupdate=utcnow)
