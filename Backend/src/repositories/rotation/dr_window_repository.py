"""Accounts whose password may have changed in a DR loss window (HA_DR.md §6.1)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import text

from src.repositories.base import BaseRepository


class DrWindowRepository(BaseRepository):
    async def rotated_in_window(self, since: datetime, until: datetime) -> set[uuid.UUID]:
        """Any non-verify rotation activity in the window: audited rotation events (queued,
        requested, changed, succeeded, failed...) and rotation jobs started, finished or
        still open. Over-listing only costs a verify; under-listing could hide a device
        holding a password this vault does not know."""
        events = await self._session.execute(
            text(
                "SELECT DISTINCT (details->>'account_id')::uuid FROM audit.events "
                "WHERE occurred_at >= :s AND occurred_at <= :u AND action LIKE 'rotation.%' "
                "AND details ? 'account_id' AND COALESCE(details->>'reason', '') <> 'verify' "
                "AND details->>'account_id' ~ "
                "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'"
            ),
            {"s": since, "u": until},
        )
        jobs = await self._session.execute(
            text(
                "SELECT DISTINCT account_id FROM access.rotation_jobs WHERE reason <> 'verify' "
                "AND account_id IS NOT NULL AND ("
                "  (started_at >= :s AND started_at <= :u) "
                "  OR (finished_at >= :s AND finished_at <= :u) "
                "  OR (finished_at IS NULL AND created_at <= :u))"
            ),
            {"s": since, "u": until},
        )
        return {r[0] for r in events.all()} | {r[0] for r in jobs.all()}

    async def existing(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, tuple[str, str]]:
        """account id -> (username, target name) for accounts this database knows."""
        if not ids:
            return {}
        rows = await self._session.execute(
            text(
                "SELECT a.id, a.username, t.name FROM inventory.accounts a "
                "JOIN inventory.targets t ON t.id = a.target_id WHERE a.id = ANY(:ids)"
            ),
            {"ids": list(ids)},
        )
        return {r[0]: (r[1], r[2]) for r in rows.all()}
