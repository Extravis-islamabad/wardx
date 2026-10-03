"""ORM models. Tables are created by the SQL files in migrations/, never by metadata."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


TZ = TIMESTAMP(timezone=True)


# ── Identity ──


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "iam"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(150))
    email: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(TZ)
    last_login_at: Mapped[datetime | None] = mapped_column(TZ)
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZ, default=utcnow, onupdate=utcnow)


class UserMfa(Base):
    __tablename__ = "user_mfa"
    __table_args__ = {"schema": "iam"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam.users.id", ondelete="CASCADE"), primary_key=True
    )
    secret_version: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_used_step: Mapped[int | None] = mapped_column(BigInteger)
    enrolled_at: Mapped[datetime | None] = mapped_column(TZ)
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)


class MfaRecoveryCode(Base):
    __tablename__ = "mfa_recovery_codes"
    __table_args__ = {"schema": "iam"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam.users.id", ondelete="CASCADE")
    )
    code_hash: Mapped[str] = mapped_column(String(64))
    used_at: Mapped[datetime | None] = mapped_column(TZ)
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)


# ── Inventory ──


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
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZ, default=utcnow, onupdate=utcnow)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = {"schema": "inventory"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory.targets.id", ondelete="CASCADE")
    )
    username: Mapped[str] = mapped_column(String(255))
    secret_type: Mapped[str] = mapped_column(String(20), default="password")
    description: Mapped[str | None] = mapped_column(Text)
    secret_version: Mapped[int] = mapped_column(Integer, default=0)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    exclusive_checkout: Mapped[bool] = mapped_column(Boolean, default=True)
    max_checkout_minutes: Mapped[int] = mapped_column(Integer, default=60)
    secret_updated_at: Mapped[datetime | None] = mapped_column(TZ)
    rotation_interval_days: Mapped[int | None] = mapped_column(Integer)
    rotate_after_checkin: Mapped[bool] = mapped_column(Boolean, default=False)
    password_length: Mapped[int] = mapped_column(Integer, default=24)
    last_rotated_at: Mapped[datetime | None] = mapped_column(TZ)
    last_rotation_status: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZ, default=utcnow, onupdate=utcnow)

    target: Mapped[Target] = relationship(lazy="joined", innerjoin=True)


# ── Vault ──


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
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)


# ── Access ──


class AccessRequest(Base):
    __tablename__ = "requests"
    __table_args__ = {"schema": "access"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory.accounts.id", ondelete="CASCADE")
    )
    requester_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("iam.users.id"))
    reason: Mapped[str] = mapped_column(Text)
    ticket_ref: Mapped[str | None] = mapped_column(String(100))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam.users.id")
    )
    decided_at: Mapped[datetime | None] = mapped_column(TZ)
    decision_note: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(TZ)
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)

    account: Mapped[Account] = relationship(lazy="joined", innerjoin=True)
    requester: Mapped[User] = relationship(
        foreign_keys=[requester_id], lazy="joined", innerjoin=True
    )
    decider: Mapped[User | None] = relationship(foreign_keys=[decided_by], lazy="joined")


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

    account: Mapped[Account] = relationship(lazy="joined", innerjoin=True)
    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined", innerjoin=True)


# ── Sessions ──


class CommandRule(Base):
    __tablename__ = "command_rules"
    __table_args__ = {"schema": "access"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory.accounts.id", ondelete="CASCADE")
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory.targets.id", ondelete="CASCADE")
    )
    platform: Mapped[str | None] = mapped_column(String(40))
    pattern: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(10), default="deny")
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)


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

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined", innerjoin=True)


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


class RotationJob(Base):
    __tablename__ = "rotation_jobs"
    __table_args__ = {"schema": "access"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory.accounts.id", ondelete="CASCADE")
    )
    reason: Mapped[str] = mapped_column(String(20))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam.users.id")
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    not_before: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    claimed_by: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(TZ)
    finished_at: Mapped[datetime | None] = mapped_column(TZ)
    from_version: Mapped[int | None] = mapped_column(Integer)
    candidate_version: Mapped[int | None] = mapped_column(Integer)
    driver: Mapped[str | None] = mapped_column(String(40))
    detail: Mapped[str | None] = mapped_column(Text)
    transcript: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam.users.id")
    )
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)

    account: Mapped[Account] = relationship(lazy="joined", innerjoin=True)


# ── Audit ──


class AuditEvent(Base):
    __tablename__ = "events"
    __table_args__ = {"schema": "audit"}

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(TZ)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_name: Mapped[str | None] = mapped_column(String(150))
    action: Mapped[str] = mapped_column(String(80))
    object_type: Mapped[str | None] = mapped_column(String(40))
    object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    outcome: Mapped[str] = mapped_column(String(20), default="success")
    source_ip: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
