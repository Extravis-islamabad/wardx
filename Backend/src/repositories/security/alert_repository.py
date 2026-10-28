"""Security alerts (security.alerts): append, list, acknowledge. Never deleted."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from src.contracts.dto.security.alert_dto import AlertDTO, AlertFilterDTO
from src.models import Alert
from src.repositories.base import BaseRepository


def _to_dto(row: Alert) -> AlertDTO:
    return AlertDTO(
        id=row.id,
        created_at=row.created_at,
        severity=row.severity,
        kind=row.kind,
        message=row.message,
        actor_id=row.actor_id,
        actor_name=row.actor_name,
        object_type=row.object_type,
        object_id=row.object_id,
        details=dict(row.details or {}),
        acknowledged_by=row.acknowledged_by,
        acknowledged_at=row.acknowledged_at,
    )


class AlertRepository(BaseRepository):
    async def add(self, values: dict[str, Any]) -> AlertDTO:
        row = Alert(**values)
        self._session.add(row)
        await self._session.flush()
        return _to_dto(row)

    async def list(
        self, filters: AlertFilterDTO, *, page: int, page_size: int
    ) -> tuple[list[AlertDTO], int]:
        conditions = []
        if filters.severity:
            conditions.append(Alert.severity == filters.severity)
        if filters.acknowledged is True:
            conditions.append(Alert.acknowledged_at.is_not(None))
        elif filters.acknowledged is False:
            conditions.append(Alert.acknowledged_at.is_(None))
        total = await self._session.scalar(
            select(func.count()).select_from(Alert).where(*conditions)
        )
        rows = await self._session.scalars(
            select(Alert)
            .where(*conditions)
            .order_by(Alert.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [_to_dto(a) for a in rows], total or 0

    async def get(self, alert_id: uuid.UUID, *, lock: bool = False) -> AlertDTO | None:
        row = await self._session.get(Alert, alert_id, with_for_update=lock or None)
        return _to_dto(row) if row else None

    async def acknowledge(self, alert_id: uuid.UUID, by: uuid.UUID | None, at: datetime) -> None:
        row = await self._session.get(Alert, alert_id)
        row.acknowledged_by = by
        row.acknowledged_at = at
        await self._session.flush()

    async def open_ids_for(self, kind: str, object_id: uuid.UUID) -> list[uuid.UUID]:
        """Unacknowledged alerts of one kind about one object."""
        return list(
            await self._session.scalars(
                select(Alert.id).where(
                    Alert.kind == kind,
                    Alert.object_id == object_id,
                    Alert.acknowledged_at.is_(None),
                )
            )
        )
