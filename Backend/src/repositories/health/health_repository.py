"""Database reachability for the readiness probe."""

from __future__ import annotations

from sqlalchemy import text

from src.repositories.base import BaseRepository


class HealthRepository(BaseRepository):
    async def ping(self) -> None:
        await self._session.execute(text("SELECT 1"))
