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
    # Direct per-user grants (iam.user_permissions), on top of the role's bundle.
    grants: frozenset[str] = frozenset()

    def can(self, codename: str) -> bool:
        """Whether the actor holds a permission codename (see src/core/permissions.py):
        through their role, or a direct grant."""
        from src.core.permissions import APP_ONLY, role_has

        if codename in APP_ONLY:
            return False  # held only by application identities, never by a user
        return role_has(self.role, codename) or codename in self.grants


# Background jobs act as the system: no user id, audited under this name.
SYSTEM_ACTOR = Actor(id=None, username="system", role=Role.ADMIN)
