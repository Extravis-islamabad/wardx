"""Who is acting: carried from the authenticated request into services and the audit trail."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from src.core.enums import Role


@dataclass(frozen=True)
class Actor:
    id: uuid.UUID | None
    username: str
    role: Role
    source_ip: str | None = None

    def can(self, codename: str) -> bool:
        """Whether the actor holds a permission codename (see src/core/permissions.py)."""
        from src.core.permissions import role_has

        return role_has(self.role, codename)


# Background jobs act as the system: no user id, audited under this name.
SYSTEM_ACTOR = Actor(id=None, username="system", role=Role.ADMIN)
