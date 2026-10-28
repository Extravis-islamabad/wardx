"""In-app notifications (notify.notifications)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func, select, update

from src.contracts.dto.notify.notification_dto import NotificationDTO
from src.models import Notification
from src.repositories.base import BaseRepository


def _to_dto(row: Notification) -> NotificationDTO:
    return NotificationDTO(
        id=row.id,
        user_id=row.user_id,
        kind=row.kind,
        title=row.title,
        body=row.body,
        object_type=row.object_type,
        object_id=row.object_id,
        created_at=row.created_at,
        read_at=row.read_at,
    )


class NotificationRepository(BaseRepository):
    async def add_many(self, user_ids: Iterable[uuid.UUID], values: dict) -> None:
        for user_id in user_ids:
            self._session.add(Notification(user_id=user_id, **values))
        await self._session.flush()

    async def list_for(
        self, user_id: uuid.UUID, *, unread_only: bool, page: int, page_size: int
    ) -> tuple[list[NotificationDTO], int]:
        conditions = [Notification.user_id == user_id]
        if unread_only:
            conditions.append(Notification.read_at.is_(None))
        total = await self._session.scalar(
            select(func.count()).select_from(Notification).where(*conditions)
        )
        rows = await self._session.scalars(
            select(Notification)
            .where(*conditions)
            .order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [_to_dto(n) for n in rows], total or 0

    async def unread_count(self, user_id: uuid.UUID) -> int:
        return (
            await self._session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            )
        ) or 0

    async def mark_read(
        self, user_id: uuid.UUID, at: datetime, notification_id: uuid.UUID | None = None
    ) -> int:
        """Mark one (or, without an id, every) unread notification of the user read."""
        stmt = update(Notification).where(
            Notification.user_id == user_id, Notification.read_at.is_(None)
        )
        if notification_id is not None:
            stmt = stmt.where(Notification.id == notification_id)
        return (await self._session.execute(stmt.values(read_at=at))).rowcount

    async def exists_for(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> bool:
        return bool(
            await self._session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.id == notification_id, Notification.user_id == user_id)
            )
        )
