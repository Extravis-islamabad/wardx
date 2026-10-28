"""Base for repositories: holds the session and ends the unit of work.

Services call ``commit`` when a unit of work is complete (an action and its
audit event together); anything uncommitted is rolled back with the session.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    async def try_advisory_lock(self, key: int) -> bool:
        """Take a transaction-scoped advisory lock; False if another session holds it."""
        return (
            await self._session.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": key})
        ).scalar_one()
