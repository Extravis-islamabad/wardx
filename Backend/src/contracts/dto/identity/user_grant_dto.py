"""Direct user grant DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class UserGrantDTO:
    id: uuid.UUID
    user_id: uuid.UUID
    codename: str
    granted_by: uuid.UUID | None
    granted_at: datetime


@dataclass(frozen=True)
class BreakGlassHolderDTO:
    user_id: uuid.UUID
    username: str
    auth_source: str
    is_active: bool
    mfa_enabled: bool

    @property
    def eligible(self) -> bool:
        """Can actually use break-glass, even with the directory down."""
        return self.auth_source == "local" and self.is_active and self.mfa_enabled
