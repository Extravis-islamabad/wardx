"""Safe and safe-member request shapes."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.core.enums import ApproverType, PrincipalType, SafePermission, TicketMode


class SafeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(None, max_length=2000)
    is_active: bool = True


class SafeUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=150)
    description: str | None = Field(None, max_length=2000)
    is_active: bool | None = None


class SafeAppFetchIn(BaseModel):
    # Let apps fetch from this safe although it requires approval for people.
    allow_app_fetch: bool = False
    # max_cache_seconds served to apps.
    app_cache_seconds: int = Field(300, ge=0, le=3600)


class SafeMemberCreate(BaseModel):
    # user: the user's id; group: the directory group's DN; role: a WardX role
    # (kept for the Default safe's migrated members; the console offers users and groups);
    # app: an application identity's id (holds only 'fetch').
    principal_type: PrincipalType
    principal_key: str = Field(min_length=1, max_length=1000)
    permissions: list[SafePermission] = Field(min_length=1, max_length=7)


class SafeMemberUpdate(BaseModel):
    permissions: list[SafePermission] = Field(min_length=1, max_length=7)


class ApprovalLevelIn(BaseModel):
    required_approvals: int = Field(1, ge=1, le=10)
    approver_type: ApproverType = ApproverType.SAFE_APPROVERS
    # user: the user's id; group: the directory group's DN; omitted for safe_approvers.
    approver_key: str | None = Field(None, max_length=1000)


class ApprovalPolicyIn(BaseModel):
    approval_required: bool = False
    # Ordered: the first is level 1.
    levels: list[ApprovalLevelIn] = Field(default_factory=list, max_length=5)
    ticket_mode: TicketMode = TicketMode.OFF
    # Full-match regex for ticket numbers; checked for safety when saved.
    ticket_pattern: str | None = Field(None, max_length=200)
    approval_window_minutes: int = Field(120, ge=1, le=10080)
    approval_multi_use: bool = False
    level_timeout_hours: int = Field(24, ge=1, le=720)
