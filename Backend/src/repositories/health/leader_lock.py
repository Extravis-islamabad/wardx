"""The scheduler leader lock: a session advisory lock on one dedicated connection (§4)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

# "WARD" + "LEAD": distinct from the migration, sweep and rotation lock keys.
LEADER_KEY = 0x5741_5244_4C45


class LeaderLock:
    """SQL for the leader's own connection. Committed after each statement, so the
    connection never sits idle in a transaction; a session lock survives commits."""

    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def try_lock(self) -> bool:
        got = (
            await self._conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LEADER_KEY})
        ).scalar_one()
        await self._conn.commit()
        return bool(got)

    async def still_held(self, node: str, now: datetime) -> bool:
        """Proves the connection is alive and still holds the lock; stamps last_seen."""
        held = (
            await self._conn.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' "
                    "AND pid = pg_backend_pid() AND granted "
                    "AND ((classid::bigint << 32) | objid::bigint) = :k)"
                ),
                {"k": LEADER_KEY},
            )
        ).scalar_one()
        if held:
            await self._conn.execute(
                text("UPDATE ha.scheduler_leader SET last_seen = :now WHERE node = :node"),
                {"now": now, "node": node},
            )
        await self._conn.commit()
        return bool(held)

    async def unlock(self) -> None:
        await self._conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LEADER_KEY})
        await self._conn.commit()
