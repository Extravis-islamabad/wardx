"""Command rule response shapes."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class CommandRuleResponse(BaseModel):
    id: uuid.UUID
    pattern: str
    description: str | None
    account_id: uuid.UUID | None
    target_id: uuid.UUID | None
    platform: str | None
    is_active: bool
    created_at: datetime


class CommandTestResultResponse(BaseModel):
    blocked: bool
    rule_id: uuid.UUID | None
    description: str | None
