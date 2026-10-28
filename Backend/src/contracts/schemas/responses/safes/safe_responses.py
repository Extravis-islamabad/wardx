"""Safe and safe-member response shapes."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class SafeResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_active: bool
    account_count: int
    member_count: int
    # The caller's effective permissions on this safe.
    my_permissions: list[str]
    # For safes.manage holders: healthy | break_glass_only | unreachable (None otherwise,
    # and for inactive safes).
    health: str | None = None
    created_at: datetime
    updated_at: datetime


class SafeMemberResponse(BaseModel):
    id: uuid.UUID
    safe_id: uuid.UUID
    principal_type: str
    principal_key: str
    display_name: str | None
    permissions: list[str]
    created_at: datetime
    updated_at: datetime


class SafeHealthResponse(BaseModel):
    safe_id: uuid.UUID
    name: str
    # healthy | break_glass_only (warning) | unreachable (critical)
    state: str
    severity: str | None
    user_members: int
    role_members: int
    group_members: int


class BreakGlassCoverageResponse(BaseModel):
    eligible_holders: int
    holders: int
    minimum: int
    # Fewer than ``minimum`` eligible holders: a single point of failure, or none at all.
    warning: bool
    message: str | None


class SafeHealthReportResponse(BaseModel):
    break_glass: BreakGlassCoverageResponse
    safes: list[SafeHealthResponse]


class DirectoryStatusResponse(BaseModel):
    enabled: bool
    reachable: bool | None
    unreachable: bool
    checked_at: datetime | None
    error: str | None
    # While unreachable: active safes nobody can reach once groups count as none.
    affected_safes: list[SafeHealthResponse]


class AttentionResponse(BaseModel):
    directory: DirectoryStatusResponse
    break_glass: BreakGlassCoverageResponse
    # Active safes that are not healthy, with severity.
    safes_needing_attention: list[SafeHealthResponse]


class ApprovalLevelResponse(BaseModel):
    position: int
    required_approvals: int
    approver_type: str
    # user levels: the user's id (for linking); group levels: the DN.
    approver_key: str | None
    # user levels: full name, else username.
    approver_name: str | None = None


class ApprovalPolicyResponse(BaseModel):
    safe_id: uuid.UUID
    approval_required: bool
    levels: list[ApprovalLevelResponse]
    ticket_mode: str
    ticket_pattern: str | None
    approval_window_minutes: int
    approval_multi_use: bool
    level_timeout_hours: int
