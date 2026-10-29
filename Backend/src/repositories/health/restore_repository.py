"""Restore verification queries and the restore drill record (ha.restore_drills)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import text

from src.repositories.base import BaseRepository


class RestoreRepository(BaseRepository):
    async def sample_accounts(self, n: int) -> list[tuple[uuid.UUID, int]]:
        """Up to ``n`` random accounts with a stored secret: (id, secret_version)."""
        rows = await self._session.execute(
            text(
                "SELECT id, secret_version FROM inventory.accounts "
                "WHERE secret_version > 0 ORDER BY random() LIMIT :n"
            ),
            {"n": n},
        )
        return [(r[0], r[1]) for r in rows.all()]

    async def rotated_after(self, point: datetime) -> list[dict[str, Any]]:
        rows = await self._session.execute(
            text(
                "SELECT a.id, a.username, t.name AS target, a.last_rotated_at "
                "FROM inventory.accounts a JOIN inventory.targets t ON t.id = a.target_id "
                "WHERE a.last_rotated_at > :p ORDER BY a.last_rotated_at"
            ),
            {"p": point},
        )
        return [
            {
                "account_id": str(r.id),
                "account": f"{r.username}@{r.target}",
                "last_rotated_at": r.last_rotated_at.isoformat(),
            }
            for r in rows.all()
        ]

    async def record_drill(
        self, *, ok: bool, restore_point: datetime | None, details: dict[str, Any]
    ) -> uuid.UUID:
        return (
            await self._session.execute(
                text(
                    "INSERT INTO ha.restore_drills (ok, restore_point, details) "
                    "VALUES (:ok, :p, CAST(:d AS JSONB)) RETURNING id"
                ),
                {"ok": ok, "p": restore_point, "d": json.dumps(details)},
            )
        ).scalar_one()
