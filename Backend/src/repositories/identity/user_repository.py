"""Users (iam.users)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.contracts.dto.identity.user_dto import UserDTO, UserFilterDTO
from src.core.enums import Role
from src.errors.exceptions import ConflictError
from src.models import User
from src.repositories.base import BaseRepository


def _to_dto(row: User) -> UserDTO:
    return UserDTO(
        id=row.id,
        username=row.username,
        email=row.email,
        full_name=row.full_name,
        password_hash=row.password_hash,
        role=row.role,
        is_active=row.is_active,
        token_version=row.token_version,
        failed_logins=row.failed_logins,
        locked_until=row.locked_until,
        last_login_at=row.last_login_at,
        auth_source=row.auth_source,
        external_id=row.external_id,
        directory_synced_at=row.directory_synced_at,
        disabled_reason=row.disabled_reason,
        created_at=row.created_at,
    )


class UserRepository(BaseRepository):
    async def list(
        self, filters: UserFilterDTO, *, page: int, page_size: int
    ) -> tuple[list[UserDTO], int]:
        conditions = []
        if filters.search:
            like = f"%{filters.search.lower()}%"
            conditions.append(
                func.lower(User.username).like(like)
                | func.lower(func.coalesce(User.full_name, "")).like(like)
            )
        total = (
            await self._session.execute(select(func.count()).select_from(User).where(*conditions))
        ).scalar_one()
        rows = await self._session.scalars(
            select(User)
            .where(*conditions)
            .order_by(func.lower(User.username))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [_to_dto(u) for u in rows], total

    async def get(self, user_id: uuid.UUID, *, lock: bool = False) -> UserDTO | None:
        """The user; ``lock`` holds the row until the transaction ends."""
        row = await self._session.get(User, user_id, with_for_update=lock or None)
        return _to_dto(row) if row else None

    async def find_by_username(self, username: str, *, lock: bool = False) -> UserDTO | None:
        """The user with this login name, ignoring case."""
        stmt = select(User).where(func.lower(User.username) == username.lower())
        if lock:
            stmt = stmt.with_for_update()
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_dto(row) if row else None

    async def directory_users(self) -> list[UserDTO]:
        """Every directory (auth_source 'ldap') user, by username. No row locks."""
        rows = await self._session.scalars(
            select(User).where(User.auth_source == "ldap").order_by(User.username)
        )
        return [_to_dto(u) for u in rows]

    async def count(self) -> int:
        return (await self._session.execute(select(func.count()).select_from(User))).scalar_one()

    async def count_active_admins(self) -> int:
        return (
            await self._session.execute(
                select(func.count())
                .select_from(User)
                .where(User.role == Role.ADMIN, User.is_active)
            )
        ).scalar_one()

    async def create(self, values: dict[str, Any]) -> UserDTO:
        row = User(**values)
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("Username already exists") from exc
        return _to_dto(row)

    async def update(self, user_id: uuid.UUID, changes: dict[str, Any]) -> UserDTO:
        row = await self._session.get(User, user_id)
        for field, value in changes.items():
            setattr(row, field, value)
        await self._session.flush()
        return _to_dto(row)
