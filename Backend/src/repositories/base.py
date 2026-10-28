"""Base for repositories: holds the session and ends the unit of work.

Services call ``commit`` when a unit of work is complete (an action and its
audit event together); anything uncommitted is rolled back with the session.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
