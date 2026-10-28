"""Check-out response shapes."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from src.contracts.schemas.responses.access.access_request_responses import (
    AccountBriefResponse,
    UserBriefResponse,
)
from src.core.enums import CheckoutStatus


class CheckoutResponse(BaseModel):
    id: uuid.UUID
    account: AccountBriefResponse
    user: UserBriefResponse
    request_id: uuid.UUID | None
    reason: str
    status: CheckoutStatus
    checked_out_at: datetime
    expires_at: datetime
    checked_in_at: datetime | None
    emergency: bool = False


class RevealedSecretResponse(BaseModel):
    checkout_id: uuid.UUID
    username: str
    secret_type: str
    value: str
    expires_at: datetime
    notice: str | None = None
