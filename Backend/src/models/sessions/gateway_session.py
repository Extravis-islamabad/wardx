"""Proxied sessions through the gateway, with recording metadata."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import TZ, Base, utcnow
from src.models.identity.user import User


class GatewaySession(Base):
    __tablename__ = "sessions"
    __table_args__ = {"schema": "access"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    checkout_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("access.checkouts.id", ondelete="SET NULL")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("iam.users.id"))
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory.accounts.id", ondelete="SET NULL")
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory.targets.id", ondelete="SET NULL")
    )
    account_username: Mapped[str] = mapped_column(String(255))
    target_name: Mapped[str] = mapped_column(String(255))
    target_address: Mapped[str] = mapped_column(String(255))
    protocol: Mapped[str] = mapped_column(String(10))
    mode: Mapped[str] = mapped_column(String(10), default="shell")
    exec_command: Mapped[str | None] = mapped_column(Text)
    client_ip: Mapped[str | None] = mapped_column(String(64))
    gateway_node: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="active")
    started_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(TZ)
    close_reason: Mapped[str | None] = mapped_column(Text)
    terminate_requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam.users.id")
    )
    terminate_requested_at: Mapped[datetime | None] = mapped_column(TZ)
    recording_path: Mapped[str | None] = mapped_column(Text)
    recording_sha256: Mapped[str | None] = mapped_column(String(64))
    recording_bytes: Mapped[int | None] = mapped_column(BigInteger)
    bytes_from_target: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes_from_user: Mapped[int] = mapped_column(BigInteger, default=0)
    commands_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, default=0)
    # The session opened its own check-out, closed again when the session ends.
    owns_checkout: Mapped[bool] = mapped_column(Boolean, default=False)
    # Encrypted recording in the object store (HA_DR.md §5.1, migration 024).
    recording_key: Mapped[str | None] = mapped_column(Text)
    recording_encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    recording_incomplete: Mapped[bool] = mapped_column(Boolean, default=False)
    recording_ciphertext_sha256: Mapped[str | None] = mapped_column(String(64))
    recording_migrated_at: Mapped[datetime | None] = mapped_column(TZ)
    recording_original_removed_at: Mapped[datetime | None] = mapped_column(TZ)

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined", innerjoin=True)
