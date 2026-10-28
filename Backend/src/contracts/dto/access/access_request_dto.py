"""Access request DTOs, and the user/account briefs every access record carries."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


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
    safe_id: uuid.UUID | None = None
    safe_name: str | None = None


@dataclass(frozen=True)
class RequestDecisionDTO:
    level: int
    approver: UserBriefDTO
    approve: bool
    note: str | None
    decided_at: datetime


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
    current_level: int = 1
    level_started_at: datetime | None = None
    policy: dict[str, Any] | None = None
    approved_at: datetime | None = None
    uses: int = 0
    decisions: tuple[RequestDecisionDTO, ...] = field(default_factory=tuple)
    # Display names of the named-user approvers in the policy snapshot, by user id.
    approver_names: dict[str, str] = field(default_factory=dict)

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
    # Requests on accounts in these safes, or the requester's own; None = no restriction.
    safe_ids: frozenset[uuid.UUID] | None = None
    include_requester_id: uuid.UUID | None = None
