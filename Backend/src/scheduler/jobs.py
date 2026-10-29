"""Background jobs (APP_ROLE api / scheduler).

With a leader elector (src/scheduler/leader.py, HA_DR.md §4) only the leader runs
jobs. Each tick still takes its own advisory lock and skips if another process holds
it, so even a brief overlap during a leadership change does not double the work.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.core.config import Settings, get_settings
from src.core.db import session_factory
from src.core.tenant import current_tenant
from src.dependencies.access import build_checkout_service
from src.dependencies.directory import build_directory_sync_service
from src.dependencies.health import build_cluster_service
from src.dependencies.rotation import build_rotation_scheduler_service, build_rotation_worker
from src.errors.exceptions import ConflictError

if TYPE_CHECKING:
    from src.scheduler.leader import LeaderElector

logger = structlog.get_logger(__name__)


async def cluster_check() -> dict[str, Any] | None:
    """Degraded synchronous replication and DR lag: conditions and alerts (HA_DR.md)."""
    async with current_tenant().session_factory()() as session:
        try:
            return await build_cluster_service(session).check()
        except Exception:
            logger.exception("cluster_check_failed")
            await session.rollback()
            return None


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


async def gateway_sweep(settings: Settings | None = None) -> int:
    """End the sessions of gateway nodes whose heartbeat is stale (HA_DR.md §5)."""
    from src.dependencies.sessions import build_gateway_node_service

    settings = settings or get_settings()
    async with current_tenant().session_factory()() as session:
        try:
            ended = await build_gateway_node_service(session).sweep_lost(
                settings.gateway_lost_seconds
            )
        except Exception:
            logger.exception("gateway_sweep_failed")
            await session.rollback()
            return 0
    if ended:
        logger.warning("gateway_sweep", ended=ended)
    return ended


def leader_only(
    elector: LeaderElector | None, job: Callable[..., Awaitable[Any]]
) -> Callable[..., Awaitable[Any]]:
    """Run ``job`` only while this node is the scheduler leader (always without an elector)."""

    @functools.wraps(job)
    async def run(*args: Any, **kwargs: Any) -> Any:
        if elector is not None and not elector.is_leader:
            return None
        return await job(*args, **kwargs)

    return run


def build_scheduler(settings: Settings, elector: LeaderElector | None = None) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        leader_only(elector, cluster_check),
        "interval",
        seconds=settings.cluster_check_seconds,
        id="cluster_check",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        leader_only(elector, gateway_sweep),
        "interval",
        seconds=max(settings.gateway_heartbeat_seconds, 2),
        kwargs={"settings": settings},
        id="gateway_sweep",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        leader_only(elector, expiry_sweep),
        "interval",
        seconds=settings.expiry_sweep_seconds,
        id="expiry_sweep",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        leader_only(elector, directory_sync_tick),
        "interval",
        seconds=60,
        id="directory_sync",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        leader_only(elector, rotation_tick),
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
