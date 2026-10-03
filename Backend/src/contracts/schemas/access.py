"""Access request, check-out, audit and dashboard schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.core.enums import CheckoutStatus, RequestStatus


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    full_name: str | None


class AccountBrief(BaseModel):
    id: uuid.UUID
    username: str
    target_id: uuid.UUID
    target_name: str
    target_address: str


class RequestCreate(BaseModel):
    account_id: uuid.UUID
    reason: str = Field(min_length=3, max_length=2000)
    ticket_ref: str | None = Field(None, max_length=100)
    duration_minutes: int = Field(60, ge=1, le=1440)


class RequestDecision(BaseModel):
    approve: bool
    note: str | None = Field(None, max_length=2000)


class RequestOut(BaseModel):
    id: uuid.UUID
    account: AccountBrief
    requester: UserBrief
    reason: str
    ticket_ref: str | None
    duration_minutes: int
    status: RequestStatus
    decided_by: UserBrief | None
    decided_at: datetime | None
    decision_note: str | None
    expires_at: datetime
    created_at: datetime


class CheckoutCreate(BaseModel):
    account_id: uuid.UUID
    reason: str | None = Field(None, max_length=2000)
    duration_minutes: int | None = Field(None, ge=1, le=1440)
    # Required when the account needs approval: the approved request to use.
    request_id: uuid.UUID | None = None


class CheckoutOut(BaseModel):
    id: uuid.UUID
    account: AccountBrief
    user: UserBrief
    request_id: uuid.UUID | None
    reason: str
    status: CheckoutStatus
    checked_out_at: datetime
    expires_at: datetime
    checked_in_at: datetime | None


class RevealedSecret(BaseModel):
    checkout_id: uuid.UUID
    username: str
    secret_type: str
    value: str
    expires_at: datetime


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    id: uuid.UUID
    occurred_at: datetime
    actor_id: uuid.UUID | None
    actor_name: str | None
    action: str
    object_type: str | None
    object_id: uuid.UUID | None
    outcome: str
    source_ip: str | None
    details: dict[str, Any]
    hash: str


class ChainVerification(BaseModel):
    ok: bool
    checked: int
    broken_at_seq: int | None
    reason: str | None


class DashboardSummary(BaseModel):
    targets: int
    accounts: int
    accounts_without_secret: int
    active_checkouts: int
    pending_requests: int
    my_active_checkouts: int
    my_open_requests: int
