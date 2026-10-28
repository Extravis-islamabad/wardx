"""User response shapes."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from src.core.enums import Role


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str | None
    full_name: str | None
    role: Role
    is_active: bool
    locked_until: datetime | None
    last_login_at: datetime | None
    auth_source: str = "local"
    disabled_reason: str | None = None
    created_at: datetime
    # Direct per-user grants (break-glass) and MFA state, filled in on the users list.
    direct_permissions: list[str] = []
    mfa_enabled: bool | None = None


class MeResponse(UserResponse):
    # Effective global permissions: the role's bundle plus direct grants. The console
    # gates on this list.
    permissions: list[str]
