"""Access request DTOs, and the user/account briefs every access record carries."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class UserBriefDTO:
    id: uuid.UUID
    username: str
    full_name: str | None


@dataclass(frozen=True)
class AccountBriefDTO:
    id: uuid.UUID
    username: str
    target_id: uuid.UUID
    target_name: str
    target_address: str


@dataclass(frozen=True)
class AccessRequestDTO:
    id: uuid.UUID
    account: AccountBriefDTO
    requester: UserBriefDTO
    reason: str
    ticket_ref: str | None
    duration_minutes: int
    status: str
    decided_by: UserBriefDTO | None
    decided_at: datetime | None
    decision_note: str | None
    expires_at: datetime
    created_at: datetime

    @property
    def account_id(self) -> uuid.UUID:
        return self.account.id

    @property
    def requester_id(self) -> uuid.UUID:
        return self.requester.id


@dataclass(frozen=True)
class AccessRequestFilterDTO:
    # Only this requester's requests; None means every request.
    requester_id: uuid.UUID | None = None
    status: str | None = None
