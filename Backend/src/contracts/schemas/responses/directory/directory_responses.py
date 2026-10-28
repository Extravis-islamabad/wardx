"""Directory configuration, test lookup and sync response shapes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from src.contracts.schemas.requests.directory.directory_requests import RoleMapping
from src.core.enums import Role


class DirectoryConfigResponse(BaseModel):
    enabled: bool
    server_url: str
    start_tls: bool
    verify_tls: bool
    ca_cert_pem: str | None
    bind_dn: str
    has_bind_password: bool
    user_base_dn: str
    user_filter: str
    attr_username: str
    attr_email: str
    attr_full_name: str
    group_base_dn: str | None
    group_filter: str | None
    role_mappings: list[RoleMapping]
    default_role: Role | None
    nested_groups: bool
    timeout_seconds: int
    sync_interval_minutes: int
    sync_max_disable_percent: int
    last_sync_at: datetime | None
    last_sync_status: str | None
    last_sync_summary: dict[str, Any] | None
    reachable: bool | None = None
    reachability_checked_at: datetime | None = None
    reachability_error: str | None = None
    updated_at: datetime


class DirectoryTestResultResponse(BaseModel):
    dn: str
    username: str
    email: str | None
    full_name: str | None
    groups: list[str]
    role: Role | None


class SyncResultResponse(BaseModel):
    status: str
    dry_run: bool
    checked: int
    disabled: list[dict[str, str]]
    enabled: list[str]
    role_changes: list[dict[str, str]]
    profile_updates: int
    problems: list[str]
    revoked_checkouts: int
    killed_sessions: int
