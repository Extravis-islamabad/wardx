"""Scheduler leader election on the test database (HA_DR.md §4): two in-process electors."""

from __future__ import annotations

import pytest

from src.core.config import get_settings
from src.scheduler.jobs import leader_only
from src.scheduler.leader import LeaderElector
from tests.integration.ha.ha_support import rows, scalar

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _elector(node: str) -> LeaderElector:
    settings = get_settings().model_copy(update={"leader_interval_seconds": 1})
    return LeaderElector(settings, node=node)


async def test_one_leader_then_takeover_after_clean_stop(app):
    a, b = _elector("sched-a"), _elector("sched-b")
    try:
        assert await a.tick() is True
        assert await b.tick() is False
        assert await a.tick() is True  # re-confirms, still leader
        assert await scalar("SELECT node FROM ha.scheduler_leader") == "sched-a"
        term_a = await scalar("SELECT term FROM ha.scheduler_leader")

        await a.stop()  # releases the lock, audited
        assert await b.tick() is True
        assert await scalar("SELECT node FROM ha.scheduler_leader") == "sched-b"
        assert await scalar("SELECT term FROM ha.scheduler_leader") == term_a + 1
        events = await rows(
            "SELECT action, details->>'node' FROM audit.events "
            "WHERE action LIKE 'scheduler.leader_%' ORDER BY seq DESC LIMIT 3"
        )
        assert ("scheduler.leader_elected", "sched-b") in events
        assert ("scheduler.leader_released", "sched-a") in events
    finally:
        await a.stop()
        await b.stop()


async def test_dead_leader_connection_hands_over(app):
    """The leader's connection dies (process or host lost): Postgres frees the lock and the
    standby takes over; the old leader steps down on its next tick instead of running on."""
    a, b = _elector("sched-c"), _elector("sched-d")
    try:
        assert await a.tick() is True
        assert await b.tick() is False
        await a._conn.invalidate()  # the connection is gone, without an unlock
        assert await b.tick() is True
        # The old leader reconnects, finds it no longer holds the lock, and steps down.
        assert await a.tick() is False
        assert a.is_leader is False
        assert await scalar("SELECT node FROM ha.scheduler_leader") == "sched-d"
    finally:
        await a.stop()
        await b.stop()


async def test_jobs_run_only_on_the_leader(app):
    ran: list[str] = []

    async def job():
        ran.append("x")

    a, b = _elector("sched-e"), _elector("sched-f")
    try:
        await a.tick()
        await b.tick()
        await leader_only(a, job)()
        await leader_only(b, job)()
        await leader_only(None, job)()  # no elector: single-process scheduler, always runs
        assert ran == ["x", "x"]
    finally:
        await a.stop()
        await b.stop()
