"""Check-out DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from src.contracts.dto.access.access_request_dto import AccountBriefDTO, UserBriefDTO


@dataclass(frozen=True)
class CheckoutDTO:
    id: uuid.UUID
    account: AccountBriefDTO
    user: UserBriefDTO
    request_id: uuid.UUID | None
    reason: str
    secret_version: int
    status: str
    checked_out_at: datetime
    expires_at: datetime
    checked_in_at: datetime | None
    emergency: bool = False

    @property
    def account_id(self) -> uuid.UUID:
        return self.account.id

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id


@dataclass(frozen=True)
class CheckoutFilterDTO:
    # Only this holder's check-outs; None means every check-out.
    user_id: uuid.UUID | None = None
    status: str | None = None


@dataclass(frozen=True)
class RevealedSecretDTO:
    checkout_id: uuid.UUID
    username: str
    secret_type: str
    value: str
    expires_at: datetime
