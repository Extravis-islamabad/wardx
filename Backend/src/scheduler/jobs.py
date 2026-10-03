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
from src.errors.exceptions import ConflictError
from src.services import access_service, directory_sync

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


async def directory_sync_tick() -> None:
    """Every minute: run the directory sync if its interval has passed."""
    async with session_factory()() as session:
        try:
            if not await directory_sync.sync_due(session):
                return
            result = await directory_sync.run_sync(session)
        except ConflictError:
            await session.rollback()  # another node is syncing, or it was just switched off
            return
        except Exception:
            logger.exception("directory_sync_failed")
            await session.rollback()
            return
        logger.info(
            "directory_sync",
            status=result.status,
            checked=result.checked,
            disabled=len(result.disabled),
            role_changes=len(result.role_changes),
        )


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
    scheduler.add_job(
        directory_sync_tick,
        "interval",
        seconds=60,
        id="directory_sync",
        max_instances=1,
        coalesce=True,
    )
    return scheduler
