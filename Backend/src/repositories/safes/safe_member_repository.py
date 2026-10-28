"""Safe members (inventory.safe_members) and permission lookups over them."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import String, and_, cast, or_, select
from sqlalchemy.exc import IntegrityError

from src.contracts.dto.safes.safe_dto import PrincipalsDTO, SafeMemberDTO
from src.core.enums import PrincipalType
from src.errors.exceptions import ConflictError
from src.models import SafeMember, User
from src.repositories.base import BaseRepository


def _to_dto(row: SafeMember, display_name: str | None = None) -> SafeMemberDTO:
    return SafeMemberDTO(
        id=row.id,
        safe_id=row.safe_id,
        principal_type=row.principal_type,
        principal_key=row.principal_key,
        permissions=tuple(row.permissions or ()),
        created_at=row.created_at,
        updated_at=row.updated_at,
        display_name=display_name,
    )


def principal_condition(p: PrincipalsDTO):
    """Rows whose principal is this person: them, their role, or one of their groups."""
    terms = [
        and_(SafeMember.principal_type == PrincipalType.ROLE, SafeMember.principal_key == p.role)
    ]
    if p.user_id is not None:
        terms.append(
            and_(
                SafeMember.principal_type == PrincipalType.USER,
                SafeMember.principal_key == str(p.user_id),
            )
        )
    if p.groups:
        terms.append(
            and_(
                SafeMember.principal_type == PrincipalType.GROUP,
                SafeMember.principal_key.in_(sorted(p.groups)),
            )
        )
    return or_(*terms)


def _with_user_name():
    """Members with the username of user members (for display)."""
    user_join = and_(
        SafeMember.principal_type == PrincipalType.USER,
        cast(User.id, String) == SafeMember.principal_key,
    )
    return select(SafeMember, User.username).outerjoin(User, user_join)


class SafeMemberRepository(BaseRepository):
    async def list_for_safe(self, safe_id: uuid.UUID) -> list[SafeMemberDTO]:
        rows = await self._session.execute(
            _with_user_name()
            .where(SafeMember.safe_id == safe_id)
            .order_by(SafeMember.principal_type, SafeMember.principal_key)
        )
        return [_to_dto(m, name) for m, name in rows.all()]

    async def get(self, member_id: uuid.UUID, *, lock: bool = False) -> SafeMemberDTO | None:
        stmt = _with_user_name().where(SafeMember.id == member_id)
        if lock:
            stmt = stmt.with_for_update(of=SafeMember)
        row = (await self._session.execute(stmt)).one_or_none()
        return _to_dto(*row) if row else None

    async def permissions_for(
        self, principals: PrincipalsDTO, safe_ids: Iterable[uuid.UUID] | None = None
    ) -> dict[uuid.UUID, set[str]]:
        """Union of permissions per safe over every membership matching the principals."""
        stmt = select(SafeMember.safe_id, SafeMember.permissions).where(
            principal_condition(principals)
        )
        if safe_ids is not None:
            stmt = stmt.where(SafeMember.safe_id.in_(list(safe_ids)))
        out: dict[uuid.UUID, set[str]] = {}
        for safe_id, perms in (await self._session.execute(stmt)).all():
            out.setdefault(safe_id, set()).update(perms or ())
        return out

    async def create(self, values: dict[str, Any]) -> uuid.UUID:
        row = SafeMember(**values)
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("This principal is already a member of the safe") from exc
        return row.id

    async def update(self, member_id: uuid.UUID, changes: dict[str, Any]) -> None:
        row = await self._session.get(SafeMember, member_id)
        for key, value in changes.items():
            setattr(row, key, value)
        await self._session.flush()

    async def delete(self, member_id: uuid.UUID) -> None:
        row = await self._session.get(SafeMember, member_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()
