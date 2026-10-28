"""Rate limits shared by every API worker (Postgres fixed-window counters).

Each hit runs in its own short transaction on a side session and commits at once, so
the count is visible to every worker immediately and a request's own rollback never
undoes it. Buckets:
- ``fetch:<app id>``: every authenticated fetch, against the app's rate_limit_per_minute;
- ``token-fail:cid:<sha256(client_id)>`` and ``token-fail:ip:<ip>``: failed token
  attempts (the client_id is hashed so an arbitrary string never lands in a key).
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.provider.rate_counter_repository import RateCounterRepository

SideSessions = Callable[[], AbstractAsyncContextManager[AsyncSession]]
WINDOW_SECONDS = 60
# One hit in this many also prunes windows older than an hour.
_PRUNE_ONE_IN = 200


def fetch_bucket(app_id: object) -> str:
    return f"fetch:{app_id}"


def client_id_bucket(client_id: str) -> str:
    return "token-fail:cid:" + hashlib.sha256(client_id.encode()).hexdigest()[:40]


def ip_bucket(ip: str | None) -> str:
    return f"token-fail:ip:{(ip or 'unknown')[:64]}"


class RateLimitService:
    def __init__(self, side_sessions: SideSessions) -> None:
        self._side_sessions = side_sessions

    async def hit(self, bucket: str, limit: int) -> tuple[bool, int]:
        """Count a hit: (still within the limit, seconds until the window ends)."""
        async with self._side_sessions() as session:
            repo = RateCounterRepository(session)
            hits, retry_after = await repo.hit(bucket, WINDOW_SECONDS)
            if random.randrange(_PRUNE_ONE_IN) == 0:  # noqa: S311 - housekeeping, not security
                await repo.prune()
            await repo.commit()
        return hits <= limit, retry_after

    async def exceeded(self, buckets: list[str], limit: int) -> int | None:
        """Seconds to wait if any bucket already reached ``limit`` this window, else None."""
        async with self._side_sessions() as session:
            repo = RateCounterRepository(session)
            for bucket in buckets:
                hits, retry_after = await repo.peek(bucket, WINDOW_SECONDS)
                if hits >= limit:
                    await repo.rollback()
                    return retry_after
            await repo.rollback()
        return None
