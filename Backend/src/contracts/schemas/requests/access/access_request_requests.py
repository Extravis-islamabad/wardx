"""Access request request shapes."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class RequestCreate(BaseModel):
    account_id: uuid.UUID
    reason: str = Field(min_length=3, max_length=2000)
    # Validated against the safe's ticket mode and pattern.
    ticket_ref: str | None = Field(None, max_length=100)
    duration_minutes: int = Field(60, ge=1, le=1440)


class RequestDecision(BaseModel):
    approve: bool
    note: str | None = Field(None, max_length=2000)
