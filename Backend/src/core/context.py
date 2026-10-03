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

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    def has_role(self, *roles: Role) -> bool:
        return self.role in roles


# Background jobs act as the system: no user id, audited under this name.
SYSTEM_ACTOR = Actor(id=None, username="system", role=Role.ADMIN)
