"""Directory configuration DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class DirectoryConfigDTO:
    enabled: bool
    server_url: str
    start_tls: bool
    verify_tls: bool
    ca_cert_pem: str | None
    bind_dn: str
    bind_secret_version: int | None
    user_base_dn: str
    user_filter: str
    attr_username: str
    attr_email: str
    attr_full_name: str
    group_base_dn: str | None
    group_filter: str | None
    role_mappings: list[dict[str, Any]]
    default_role: str | None
    timeout_seconds: int
    sync_interval_minutes: int
    sync_max_disable_percent: int
    last_sync_at: datetime | None
    last_sync_status: str | None
    last_sync_summary: dict[str, Any] | None
    updated_by: uuid.UUID | None
    updated_at: datetime

    @property
    def has_bind_password(self) -> bool:
        return self.bind_secret_version is not None
