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
    safe_id: uuid.UUID | None = None
    safe_name: str | None = None


class RequestLevelResponse(BaseModel):
    position: int
    required_approvals: int
    approver_type: str
    approver_key: str | None
    # approved | denied | current | waiting
    state: str
    approvals: int


class RequestDecisionResponse(BaseModel):
    level: int
    approver: UserBriefResponse
    approve: bool
    note: str | None
    decided_at: datetime


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
    # Pending: the current level's deadline. Approved: valid_until (end of the window).
    expires_at: datetime
    created_at: datetime
    current_level: int = 1
    level_count: int = 0
    levels: list[RequestLevelResponse] = []
    decisions: list[RequestDecisionResponse] = []
    approved_at: datetime | None = None
    valid_until: datetime | None = None
    multi_use: bool = False
    uses: int = 0
