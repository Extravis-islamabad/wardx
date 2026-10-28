"""Background jobs (APP_ROLE api / scheduler).

Each tick takes a transaction advisory lock and skips if another process holds
it, so running several schedulers does not double the work.
"""

from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.core.config import Settings, get_settings
from src.core.db import session_factory
from src.core.tenant import current_tenant
from src.dependencies.access import build_checkout_service
from src.dependencies.directory import build_directory_sync_service
from src.dependencies.rotation import build_rotation_scheduler_service, build_rotation_worker
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


async def rotation_tick(settings: Settings | None = None) -> dict[str, int]:
    """Rotation housekeeping, then run due jobs (ROTATION.md sections 4 to 6).

    The empty-password scan and release checks touch no device and always run. Due
    rotations and verifies are queued only while WARDX_ROTATION_ENABLED is on, and the
    engine refuses every job (without connecting) while either switch is off.
    """
    settings = settings or get_settings()
    sessions = current_tenant().session_factory()
    result: dict[str, int] = {}
    for name, step in (
        ("scan", lambda s: s.scan_empty_passwords()),
        ("release", lambda s: s.release_waiting()),
        (
            "enqueue",
            lambda s: s.enqueue_due(
                enabled=settings.rotation_enabled, jitter_seconds=settings.rotation_jitter_seconds
            ),
        ),
    ):
        async with sessions() as session:
            try:
                out = await step(build_rotation_scheduler_service(session))
            except Exception:
                logger.exception("rotation_tick_failed", step=name)
                await session.rollback()
                continue
        if isinstance(out, dict):
            result.update({f"{name}_{k}": v for k, v in out.items()})
        else:
            result[name] = out
    result["ran"] = await build_rotation_worker(settings).run_once()
    if any(result.values()):
        logger.info("rotation_tick", **result)
    return result


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
    scheduler.add_job(
        rotation_tick,
        "interval",
        seconds=settings.rotation_tick_seconds,
        # The settings this scheduler was built with, not whatever get_settings() returns
        # at tick time: switches, jitter and worker limits must match the scheduler.
        kwargs={"settings": settings},
        id="rotation",
        max_instances=1,
        coalesce=True,
    )
    return scheduler
