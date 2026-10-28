"""User administration and first-admin bootstrap.

Rules:
- The last active administrator cannot be demoted or deactivated, and nobody
  deactivates their own account.
- A role or access change, or a password reset, signs the user out everywhere.
- Directory users' passwords live in the directory, never here.
"""

from __future__ import annotations

import os
import secrets
import uuid
from typing import Any

import structlog

from src.contracts.dto.identity.user_dto import UserDTO, UserFilterDTO
from src.core.config import DEV_STATE_DIR, Settings
from src.core.context import SYSTEM_ACTOR, Actor
from src.core.enums import Role
from src.core.security import hash_password
from src.errors.exceptions import ConflictError, NotFoundError
from src.repositories.identity.user_repository import UserRepository
from src.services.audit.audit_service import AuditService

logger = structlog.get_logger(__name__)


def _plain(value: Any) -> Any:
    return value.value if isinstance(value, Role) else value


class UserService:
    def __init__(self, users: UserRepository, audit: AuditService) -> None:
        self._users = users
        self._audit = audit

    async def list(
        self, filters: UserFilterDTO, *, page: int, page_size: int
    ) -> tuple[list[UserDTO], int]:
        return await self._users.list(filters, page=page, page_size=page_size)

    async def get(self, user_id: uuid.UUID, *, lock: bool = False) -> UserDTO:
        user = await self._users.get(user_id, lock=lock)
        if user is None:
            raise NotFoundError("User not found")
        return user

    async def create(
        self,
        actor: Actor,
        *,
        username: str,
        password: str,
        email: str | None,
        full_name: str | None,
        role: Role,
    ) -> UserDTO:
        user = await self._users.create(
            {
                "username": username,
                "email": email,
                "full_name": full_name,
                "role": role.value,
                "password_hash": await hash_password(password),
            }
        )
        await self._audit.record(
            actor,
            "user.create",
            object_type="user",
            object_id=user.id,
            details={"username": user.username, "role": user.role},
        )
        await self._users.commit()
        return user

    async def update(self, actor: Actor, user_id: uuid.UUID, changes: dict[str, Any]) -> UserDTO:
        user = await self.get(user_id, lock=True)
        demoting = user.role == Role.ADMIN and (
            changes.get("role", Role.ADMIN) != Role.ADMIN or changes.get("is_active") is False
        )
        if demoting and user.is_active and await self._users.count_active_admins() <= 1:
            raise ConflictError("Cannot remove the last active administrator")
        if user.id == actor.id and changes.get("is_active") is False:
            raise ConflictError("You cannot deactivate your own account")

        values = {field: _plain(value) for field, value in changes.items()}
        if "is_active" in changes:
            values["disabled_reason"] = None if values["is_active"] else "admin"
        if "role" in changes or changes.get("is_active") is False:
            # Role or access changed: make existing tokens re-authenticate.
            values["token_version"] = user.token_version + 1
        updated = await self._users.update(user.id, values)
        await self._audit.record(
            actor,
            "user.update",
            object_type="user",
            object_id=user.id,
            details={k: _plain(v) for k, v in changes.items()},
        )
        await self._users.commit()
        return updated

    async def reset_password(self, actor: Actor, user_id: uuid.UUID, new_password: str) -> None:
        user = await self.get(user_id, lock=True)
        if user.auth_source != "local":
            raise ConflictError("This user signs in through the directory; reset it there")
        await self._users.update(
            user.id,
            {
                "password_hash": await hash_password(new_password),
                "token_version": user.token_version + 1,
                "failed_logins": 0,
                "locked_until": None,
            },
        )
        await self._audit.record(
            actor, "user.password_reset", object_type="user", object_id=user.id
        )
        await self._users.commit()

    async def bootstrap_admin(self, settings: Settings) -> None:
        """Create the first administrator when the user table is empty."""
        if await self._users.count() > 0:
            return
        password = settings.bootstrap_admin_password
        if not password:
            if settings.is_production:
                logger.warning(
                    "bootstrap_admin_skipped", reason="WARDX_BOOTSTRAP_ADMIN_PASSWORD not set"
                )
                return
            # Development: generate one and leave it in a 0600 file, never in the log.
            password = secrets.token_urlsafe(18)
            DEV_STATE_DIR.mkdir(mode=0o700, exist_ok=True)
            path = DEV_STATE_DIR / "initial-admin-password"
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write(password + "\n")
            logger.info("bootstrap_admin_password_written", path=str(path))
        user = await self._users.create(
            {
                "username": settings.bootstrap_admin_username,
                "role": Role.ADMIN.value,
                "full_name": "Administrator",
                "password_hash": await hash_password(password),
            }
        )
        await self._audit.record(
            SYSTEM_ACTOR,
            "user.bootstrap_admin",
            object_type="user",
            object_id=user.id,
            details={"username": user.username},
        )
        await self._users.commit()
        logger.info("bootstrap_admin_created", username=user.username)
