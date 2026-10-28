"""Access request response shapes, and the briefs every access record carries."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from src.core.enums import RequestStatus


class UserBriefResponse(BaseModel):
    id: uuid.UUID
    username: str
    full_name: str | None


class AccountBriefResponse(BaseModel):
    id: uuid.UUID
    username: str
    target_id: uuid.UUID
    target_name: str
    target_address: str


class AccessRequestResponse(BaseModel):
    id: uuid.UUID
    account: AccountBriefResponse
    requester: UserBriefResponse
    reason: str
    ticket_ref: str | None
    duration_minutes: int
    status: RequestStatus
    decided_by: UserBriefResponse | None
    decided_at: datetime | None
    decision_note: str | None
    expires_at: datetime
    created_at: datetime
