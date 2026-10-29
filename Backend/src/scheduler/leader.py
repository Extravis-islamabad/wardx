"""Scheduler leader election (HA_DR.md §4).

Every scheduler node tries ``pg_try_advisory_lock(LEADER_KEY)`` every
``leader_interval_seconds`` on a connection of its own. The node holding the lock is the
leader and runs the jobs; the others run nothing. The lock lives as long as that
connection: if the leader dies or its connection drops, PostgreSQL releases it and a
standby takes it on its next try. Server-side TCP keepalives (5 s idle, 5 s interval,
2 probes) bound how long a vanished leader host keeps the lock to about 15 seconds.

The leader re-checks on every tick that its connection is alive and still holds the lock,
within the same interval; any failure makes it step down at once (it stops running jobs
before the server could hand the lock to anyone else). Every election is audited.
"""

from __future__ import annotations

import asyncio
import contextlib

import structlog
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import Settings
from src.core.tenant import current_tenant
from src.models import utcnow
from src.repositories.health.leader_lock import LeaderLock

logger = structlog.get_logger(__name__)

KEEPALIVE_SETTINGS = {
    "tcp_keepalives_idle": "5",
    "tcp_keepalives_interval": "5",
    "tcp_keepalives_count": "2",
}


class LeaderElector:
    def __init__(self, settings: Settings, *, node: str | None = None) -> None:
        self.settings = settings
        self.node = node or settings.node()
        self.interval = settings.leader_interval_seconds
        self._engine: AsyncEngine | None = None
        self._conn: AsyncConnection | None = None
        self._leader = False
        self._task: asyncio.Task | None = None
        self.term: int | None = None

    @property
    def is_leader(self) -> bool:
        return self._leader

    def _get_engine(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = create_async_engine(
                self.settings.database_url,
                poolclass=NullPool,
                connect_args={
                    "server_settings": {
                        **KEEPALIVE_SETTINGS,
                        "application_name": f"wardx-leader:{self.node}"[:63],
                    },
                    "timeout": max(self.interval, 2),
                },
            )
        return self._engine

    async def tick(self) -> bool:
        """One attempt: become leader, or confirm leadership. Returns is_leader."""
        timeout = max(self.interval, 2)
        try:
            if self._conn is None:
                self._conn = await asyncio.wait_for(self._get_engine().connect(), timeout)
            lock = LeaderLock(self._conn)
            if self._leader:
                if not await asyncio.wait_for(lock.still_held(self.node, utcnow()), timeout):
                    raise RuntimeError("leader lock no longer held")
            elif await asyncio.wait_for(lock.try_lock(), timeout):
                self._leader = True
                await self._record_elected()
        except Exception as exc:
            await self._step_down(type(exc).__name__)
        return self._leader

    async def _record_elected(self) -> None:
        from src.dependencies.health import build_cluster_service

        try:
            async with current_tenant().session_factory()() as session:
                self.term = await build_cluster_service(session).record_elected(self.node)
        except Exception:
            # Leadership stands (the lock decides); only the record failed.
            logger.exception("scheduler_leader_record_failed", node=self.node)
        logger.warning("scheduler_leader_elected", node=self.node, term=self.term)

    async def _step_down(self, reason: str) -> None:
        was_leader = self._leader
        self._leader = False
        if self._conn is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._conn.invalidate(), 2)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._conn.close(), 2)
        self._conn = None
        if was_leader:
            logger.warning("scheduler_leadership_lost", node=self.node, reason=reason)

    async def _loop(self) -> None:
        while True:
            await self.tick()
            await asyncio.sleep(self.interval)

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Release leadership on a clean shutdown (audited) so a standby takes over at once."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        if self._leader and self._conn is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(LeaderLock(self._conn).unlock(), 3)
            with contextlib.suppress(Exception):
                from src.dependencies.health import build_cluster_service

                async with current_tenant().session_factory()() as session:
                    await build_cluster_service(session).record_released(self.node, "shutdown")
        await self._step_down("shutdown")
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
