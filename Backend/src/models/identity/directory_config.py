"""The single LDAP / Active Directory connection and sync settings row."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import TZ, Base, utcnow


class DirectoryConfig(Base):
    __tablename__ = "directory_config"
    __table_args__ = {"schema": "iam"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    server_url: Mapped[str] = mapped_column(Text)
    start_tls: Mapped[bool] = mapped_column(Boolean, default=False)
    verify_tls: Mapped[bool] = mapped_column(Boolean, default=True)
    ca_cert_pem: Mapped[str | None] = mapped_column(Text)
    bind_dn: Mapped[str] = mapped_column(Text)
    bind_secret_version: Mapped[int | None] = mapped_column(Integer)
    user_base_dn: Mapped[str] = mapped_column(Text)
    user_filter: Mapped[str] = mapped_column(Text)
    attr_username: Mapped[str] = mapped_column(String(64))
    attr_email: Mapped[str] = mapped_column(String(64), default="mail")
    attr_full_name: Mapped[str] = mapped_column(String(64), default="displayName")
    group_base_dn: Mapped[str | None] = mapped_column(Text)
    group_filter: Mapped[str | None] = mapped_column(Text)
    role_mappings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    nested_groups: Mapped[bool] = mapped_column(Boolean, default=False)
    default_role: Mapped[str | None] = mapped_column(String(20))
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10)
    sync_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    sync_max_disable_percent: Mapped[int] = mapped_column(Integer, default=20)
    last_sync_at: Mapped[datetime | None] = mapped_column(TZ)
    last_sync_status: Mapped[str | None] = mapped_column(String(20))
    last_sync_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reachable: Mapped[bool | None] = mapped_column(Boolean)
    reachability_checked_at: Mapped[datetime | None] = mapped_column(TZ)
    reachability_error: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(TZ, default=utcnow, onupdate=utcnow)
