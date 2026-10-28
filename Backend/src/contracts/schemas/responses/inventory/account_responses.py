"""Account response shapes."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class TargetBriefResponse(BaseModel):
    id: uuid.UUID
    name: str
    address: str
    platform: str
    protocol: str


class AccountResponse(BaseModel):
    id: uuid.UUID
    target: TargetBriefResponse
    username: str
    secret_type: str
    description: str | None
    has_secret: bool
    secret_version: int
    secret_updated_at: datetime | None
    requires_approval: bool
    exclusive_checkout: bool
    max_checkout_minutes: int
    active_checkouts: int = 0
    created_at: datetime
