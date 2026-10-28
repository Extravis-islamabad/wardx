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
