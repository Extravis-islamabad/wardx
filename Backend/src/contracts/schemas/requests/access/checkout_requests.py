"""Check-out request shapes."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class CheckoutCreate(BaseModel):
    account_id: uuid.UUID
    reason: str | None = Field(None, max_length=2000)
    duration_minutes: int | None = Field(None, ge=1, le=1440)
    # Required when the account needs approval: the approved request to use.
    request_id: uuid.UUID | None = None
