"""Background jobs (APP_ROLE api / scheduler).

Each tick takes a transaction advisory lock and skips if another process holds
it, so running several schedulers does not double the work.
"""

from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text

from src.core.config import Settings
from src.core.db import session_factory
from src.services import access_service

logger = structlog.get_logger(__name__)

_EXPIRY_LOCK_KEY = 0x5741_5244_00E1


async def expiry_sweep() -> None:
    async with session_factory()() as session:
        got = (
            await session.execute(
                text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": _EXPIRY_LOCK_KEY}
            )
        ).scalar_one()
        if not got:
            await session.rollback()
            return
        try:
            result = await access_service.expire_overdue(session)
        except Exception:
            logger.exception("expiry_sweep_failed")
            await session.rollback()
            return
        if any(result.values()):
            logger.info("expiry_sweep", **result)


def build_scheduler(settings: Settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        expiry_sweep,
        "interval",
        seconds=settings.expiry_sweep_seconds,
        id="expiry_sweep",
        max_instances=1,
        coalesce=True,
    )
    return scheduler
