"""Fixed-window counters in iam.rate_counters, shared by every API worker.

The window is computed from the database clock, so workers on different hosts agree on
it. One upsert per hit: concurrent hits on a bucket serialise on its row and each sees
the count including itself.
"""

from __future__ import annotations

from sqlalchemy import text

from src.repositories.base import BaseRepository

# The current window's start, from the database clock: floor(now / w) * w.
_HIT = """
INSERT INTO iam.rate_counters (bucket, window_start, hits)
VALUES (:bucket,
        to_timestamp(floor(extract(epoch FROM clock_timestamp()) / CAST(:w AS integer))
                     * CAST(:w AS integer)),
        1)
ON CONFLICT (bucket, window_start) DO UPDATE SET hits = iam.rate_counters.hits + 1
RETURNING hits,
          GREATEST(1, CEIL(extract(epoch FROM (
              window_start + make_interval(secs => CAST(:w AS integer)) - clock_timestamp()
          ))))::int AS retry_after
"""

_PEEK = """
WITH w AS (
    SELECT to_timestamp(floor(extract(epoch FROM clock_timestamp()) / CAST(:w AS integer))
                        * CAST(:w AS integer)) AS start
)
SELECT COALESCE((SELECT hits FROM iam.rate_counters c
                 WHERE c.bucket = :bucket AND c.window_start = w.start), 0) AS hits,
       GREATEST(1, CEIL(extract(epoch FROM (
           w.start + make_interval(secs => CAST(:w AS integer)) - clock_timestamp()
       ))))::int AS retry_after
FROM w
"""

_PRUNE = "DELETE FROM iam.rate_counters WHERE window_start < clock_timestamp() - interval '1 hour'"


class RateCounterRepository(BaseRepository):
    async def hit(self, bucket: str, window_seconds: int) -> tuple[int, int]:
        """Count one hit; (hits in this window including this one, seconds to its end)."""
        row = (
            await self._session.execute(text(_HIT), {"bucket": bucket, "w": window_seconds})
        ).one()
        return int(row.hits), int(row.retry_after)

    async def peek(self, bucket: str, window_seconds: int) -> tuple[int, int]:
        row = (
            await self._session.execute(text(_PEEK), {"bucket": bucket, "w": window_seconds})
        ).one()
        return int(row.hits), int(row.retry_after)

    async def prune(self) -> None:
        await self._session.execute(text(_PRUNE))
