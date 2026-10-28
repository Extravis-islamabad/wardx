"""Safes (inventory.safes), with their account and member counts."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.contracts.dto.safes.safe_dto import SafeDTO, SafeFilterDTO
from src.errors.exceptions import ConflictError
from src.models import Account, Safe, SafeMember
from src.repositories.base import BaseRepository

_DUPLICATE = "A safe with this name already exists"


def _to_dto(row: Safe, accounts: int = 0, members: int = 0) -> SafeDTO:
    return SafeDTO(
        id=row.id,
        name=row.name,
        description=row.description,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
        account_count=accounts,
        member_count=members,
        allow_app_fetch=row.allow_app_fetch,
        app_cache_seconds=row.app_cache_seconds,
        approval_required=row.approval_required,
    )


def _counts():
    accounts = (
        select(func.count())
        .select_from(Account)
        .where(Account.safe_id == Safe.id)
        .scalar_subquery()
    )
    members = (
        select(func.count())
        .select_from(SafeMember)
        .where(SafeMember.safe_id == Safe.id)
        .scalar_subquery()
    )
    return accounts, members


class SafeRepository(BaseRepository):
    async def list(
        self, filters: SafeFilterDTO, *, page: int, page_size: int
    ) -> tuple[list[SafeDTO], int]:
        conditions = []
        if filters.ids is not None:
            conditions.append(Safe.id.in_(filters.ids))
        if filters.search:
            conditions.append(func.lower(Safe.name).like(f"%{filters.search.lower()}%"))
        total = await self._session.scalar(
            select(func.count()).select_from(Safe).where(*conditions)
        )
        accounts, members = _counts()
        rows = await self._session.execute(
            select(Safe, accounts, members)
            .where(*conditions)
            .order_by(func.lower(Safe.name))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [_to_dto(s, a, m) for s, a, m in rows.all()], total or 0

    async def get(self, safe_id: uuid.UUID, *, lock: bool = False) -> SafeDTO | None:
        accounts, members = _counts()
        stmt = select(Safe, accounts, members).where(Safe.id == safe_id)
        if lock:
            stmt = stmt.with_for_update(of=Safe)
        row = (await self._session.execute(stmt)).one_or_none()
        return _to_dto(*row) if row else None

    async def active_ids(self) -> set[uuid.UUID]:
        return set(await self._session.scalars(select(Safe.id).where(Safe.is_active)))

    async def create(self, values: dict[str, Any]) -> uuid.UUID:
        row = Safe(**values)
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError(_DUPLICATE) from exc
        return row.id

    async def update(self, safe_id: uuid.UUID, changes: dict[str, Any]) -> None:
        row = await self._session.get(Safe, safe_id)
        for key, value in changes.items():
            setattr(row, key, value)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError(_DUPLICATE) from exc
