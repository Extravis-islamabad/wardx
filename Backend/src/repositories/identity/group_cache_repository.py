"""Cached directory groups per user (iam.user_group_cache)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from src.models import UserGroupCache
from src.repositories.base import BaseRepository


class GroupCacheRepository(BaseRepository):
    async def get(self, user_id: uuid.UUID) -> tuple[frozenset[str], datetime] | None:
        row = (
            await self._session.execute(
                select(UserGroupCache.groups, UserGroupCache.fetched_at).where(
                    UserGroupCache.user_id == user_id
                )
            )
        ).one_or_none()
        return (frozenset(row.groups or ()), row.fetched_at) if row else None

    async def store(self, user_id: uuid.UUID, groups: Iterable[str], at: datetime) -> None:
        values = {"user_id": user_id, "groups": sorted(set(groups)), "fetched_at": at}
        await self._session.execute(
            insert(UserGroupCache)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[UserGroupCache.user_id],
                set_={"groups": values["groups"], "fetched_at": at},
            )
        )

    async def clear(self, user_id: uuid.UUID) -> None:
        await self._session.execute(delete(UserGroupCache).where(UserGroupCache.user_id == user_id))
