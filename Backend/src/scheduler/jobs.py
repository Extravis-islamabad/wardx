"""Background jobs (APP_ROLE api / scheduler).

Each tick takes a transaction advisory lock and skips if another process holds
it, so running several schedulers does not double the work.
"""

from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.core.config import Settings
from src.core.db import session_factory
from src.dependencies.access import build_checkout_service
from src.dependencies.directory import build_directory_sync_service
from src.errors.exceptions import ConflictError

logger = structlog.get_logger(__name__)


async def expiry_sweep() -> None:
    async with session_factory()() as session:
        try:
            result = await build_checkout_service(session).sweep()
        except Exception:
            logger.exception("expiry_sweep_failed")
            await session.rollback()
            return
        if result is None:
            await session.rollback()  # another scheduler holds the sweep lock
            return
        if any(result.values()):
            logger.info("expiry_sweep", **result)


async def directory_sync_tick() -> None:
    """Every minute: run the directory sync if its interval has passed."""
    async with session_factory()() as session:
        try:
            service = build_directory_sync_service(session)
            if not await service.sync_due():
                return
            result = await service.run_sync()
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
