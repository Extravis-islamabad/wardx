"""Targets (inventory.targets)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from src.contracts.dto.inventory.target_dto import TargetDTO, TargetFilterDTO
from src.errors.exceptions import ConflictError
from src.models import Target
from src.repositories.base import BaseRepository


def _to_dto(row: Target) -> TargetDTO:
    return TargetDTO(
        id=row.id,
        name=row.name,
        address=row.address,
        platform=row.platform,
        protocol=row.protocol,
        port=row.port,
        description=row.description,
        tags=list(row.tags or []),
        external_ref=row.external_ref,
        is_active=row.is_active,
        ssh_host_key_fingerprint=row.ssh_host_key_fingerprint,
        ssh_host_key_learned_at=row.ssh_host_key_learned_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class TargetRepository(BaseRepository):
    async def list(
        self, filters: TargetFilterDTO, *, page: int, page_size: int
    ) -> tuple[list[TargetDTO], int]:
        conditions = []
        if filters.search:
            like = f"%{filters.search.lower()}%"
            conditions.append(
                or_(func.lower(Target.name).like(like), func.lower(Target.address).like(like))
            )
        if filters.platform:
            conditions.append(Target.platform == filters.platform)
        total = await self._session.scalar(
            select(func.count()).select_from(Target).where(*conditions)
        )
        rows = await self._session.scalars(
            select(Target)
            .where(*conditions)
            .order_by(func.lower(Target.name))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [_to_dto(r) for r in rows], total or 0

    async def get(self, target_id: uuid.UUID) -> TargetDTO | None:
        row = await self._session.get(Target, target_id)
        return _to_dto(row) if row else None

    async def create(self, values: dict[str, Any]) -> TargetDTO:
        row = Target(**values)
        self._session.add(row)
        await self._flush_unique()
        return _to_dto(row)

    async def update(self, target_id: uuid.UUID, changes: dict[str, Any]) -> TargetDTO | None:
        row = await self._session.get(Target, target_id)
        if row is None:
            return None
        for field, value in changes.items():
            setattr(row, field, value)
        await self._flush_unique()
        return _to_dto(row)

    async def delete(self, target_id: uuid.UUID) -> None:
        row = await self._session.get(Target, target_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    async def _flush_unique(self) -> None:
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("A target with this name already exists") from exc
