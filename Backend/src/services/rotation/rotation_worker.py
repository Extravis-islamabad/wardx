"""Claims due rotation jobs and runs them on a bounded worker pool.

Claiming is one short transaction per job (FOR UPDATE SKIP LOCKED, per-target lock),
so several scheduler processes share the queue. A claimed job carries a lease; if
its worker dies, the lease expires and the next claim resumes it from its state.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models import utcnow
from src.repositories.rotation.rotation_job_repository import RotationJobRepository
from src.services.rotation.rotation_engine import RotationEngine, SimulatedCrash

logger = structlog.get_logger(__name__)


class RotationWorker:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        engine: RotationEngine,
        *,
        worker_id: str,
        pool_size: int = 4,
        lease_seconds: int = 600,
        repo_factory: Callable[[AsyncSession], RotationJobRepository] = RotationJobRepository,
    ) -> None:
        self._sessions = sessions
        self.engine = engine
        self.worker_id = worker_id
        self.pool_size = pool_size
        self._lease = timedelta(seconds=lease_seconds)
        self._repo_factory = repo_factory

    async def claim(self, hold: frozenset[str] = frozenset()) -> uuid.UUID | None:
        async with self._sessions() as session:
            repo = self._repo_factory(session)
            job_id = await repo.claim(
                self.worker_id, utcnow(), self._lease, hold_pending_reasons=hold
            )
            await repo.commit()
            return job_id

    async def _run(self, job_id: uuid.UUID) -> None:
        try:
            await self.engine.run(job_id)
        except SimulatedCrash:
            raise
        except Exception:
            # The lease expires and a later claim resumes the job from its last state.
            logger.exception("rotation_job_crashed", job_id=str(job_id))

    async def run_once(self, hold: frozenset[str] = frozenset()) -> int:
        """Claim up to ``pool_size`` jobs (one per target) and run them concurrently.
        ``hold``: reasons whose pending jobs wait (the DR lag pause, HA_DR.md §6.1)."""
        claimed: list[uuid.UUID] = []
        for _ in range(self.pool_size):
            job_id = await self.claim(hold)
            if job_id is None:
                break
            claimed.append(job_id)
        if claimed:
            await asyncio.gather(*(self._run(j) for j in claimed))
        return len(claimed)
