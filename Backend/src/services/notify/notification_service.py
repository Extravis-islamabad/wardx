"""In-app notifications. No email.

``notify`` adds rows in the caller's transaction (the caller commits with the change it
reports). People only ever see and mark their own notifications.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from src.contracts.dto.notify.notification_dto import NotificationDTO
from src.core.context import Actor
from src.errors.exceptions import NotFoundError
from src.models import utcnow
from src.repositories.notify.notification_repository import NotificationRepository


class NotificationService:
    def __init__(self, notifications: NotificationRepository) -> None:
        self._notifications = notifications

    async def notify(
        self,
        user_ids: Iterable[uuid.UUID],
        *,
        kind: str,
        title: str,
        body: str | None = None,
        object_type: str | None = None,
        object_id: uuid.UUID | None = None,
    ) -> None:
        await self._notifications.add_many(
            sorted(set(user_ids)),
            {
                "kind": kind,
                "title": title,
                "body": body,
                "object_type": object_type,
                "object_id": object_id,
            },
        )

    async def list_mine(
        self, actor: Actor, *, unread_only: bool, page: int, page_size: int
    ) -> tuple[list[NotificationDTO], int]:
        return await self._notifications.list_for(
            actor.id, unread_only=unread_only, page=page, page_size=page_size
        )

    async def unread_count(self, actor: Actor) -> int:
        return await self._notifications.unread_count(actor.id)

    async def mark_read(self, actor: Actor, notification_id: uuid.UUID) -> None:
        if not await self._notifications.exists_for(actor.id, notification_id):
            raise NotFoundError("Notification not found")
        await self._notifications.mark_read(actor.id, utcnow(), notification_id)
        await self._notifications.commit()

    async def mark_all_read(self, actor: Actor) -> int:
        count = await self._notifications.mark_read(actor.id, utcnow())
        await self._notifications.commit()
        return count
