"""Safe and safe-member DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class SafeDTO:
    id: uuid.UUID
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    account_count: int = 0
    member_count: int = 0


@dataclass(frozen=True)
class SafeMemberDTO:
    id: uuid.UUID
    safe_id: uuid.UUID
    principal_type: str
    principal_key: str
    permissions: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    # For user members: the user's name, for display.
    display_name: str | None = None

    def audit_view(self) -> dict:
        return {
            "principal_type": self.principal_type,
            "principal_key": self.principal_key,
            "permissions": sorted(self.permissions),
        }


@dataclass(frozen=True)
class PrincipalsDTO:
    """Who someone is, for evaluating safe membership."""

    user_id: uuid.UUID | None
    role: str
    groups: frozenset[str] = field(default_factory=frozenset)
    # False when directory groups could not be verified (directory unreachable).
    groups_verified: bool = True


@dataclass(frozen=True)
class SafeFilterDTO:
    search: str | None = None
    # None = every safe (safes.manage); otherwise only these.
    ids: frozenset[uuid.UUID] | None = None
