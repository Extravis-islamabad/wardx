"""Scheduled rotation and scheduled verify through the real background scheduler
(ROTATION.md §14, fix 2).

Nothing here calls rotation_tick or the worker directly: APScheduler, as built by
src/scheduler/jobs.py, ticks on its own and the jobs are queued, claimed and run
the way a production scheduler process does it.
"""

from __future__ import annotations

import asyncio

import pytest

from src.core.config import get_settings
from src.scheduler.jobs import build_scheduler
from tests.integration.rotation.rotation_support import START, sql

pytestmark = pytest.mark.asyncio(loop_scope="session")

FINAL = {"succeeded", "failed", "needs_attention", "cancelled", "resolved"}


async def _finished_job(account_id: str, reason: str) -> dict:
    """Poll until the newest job of this reason for the account is final."""
    while True:
        rows = await sql(
            "SELECT id, status, reason FROM access.rotation_jobs "
            "WHERE account_id = :a AND reason = :r ORDER BY created_at DESC LIMIT 1",
            a=account_id,
            r=reason,
        )
        if rows and rows[0]["status"] in FINAL:
            return rows[0]
        await asyncio.sleep(0.25)


async def test_scheduled_rotation_and_verify_run_through_the_real_scheduler(rotlab):
    safe_id = await rotlab.safe(rotation_interval_days=1, verify_interval_hours=1)
    to_rotate = await rotlab.account(safe_id=safe_id)
    to_verify = await rotlab.account(safe_id=safe_id)

    # Keep the run contained: every other account in the shared test database is made
    # not due, so the scheduler only finds the two accounts above.
    await sql(
        "UPDATE inventory.accounts SET last_rotated_at = NOW(), last_verified_at = NOW(), "
        "last_verify_attempt_at = NOW() WHERE id NOT IN (:a, :b)",
        a=to_rotate["id"],
        b=to_verify["id"],
    )
    # Due for rotation (interval of 1 day passed); verified recently, so not due for verify.
    await sql(
        "UPDATE inventory.accounts SET last_rotated_at = NOW() - INTERVAL '2 days', "
        "last_verified_at = NOW(), last_verify_attempt_at = NOW() WHERE id = :a",
        a=to_rotate["id"],
    )
    # Not due for rotation; last verify 2 hours ago with a 1-hour interval: due.
    await sql(
        "UPDATE inventory.accounts SET last_rotated_at = NOW(), "
        "last_verified_at = NOW() - INTERVAL '2 hours', "
        "last_verify_attempt_at = NOW() - INTERVAL '2 hours' WHERE id = :b",
        b=to_verify["id"],
    )

    settings = get_settings().model_copy(
        update={"rotation_enabled": True, "rotation_tick_seconds": 1, "rotation_jitter_seconds": 0}
    )
    scheduler = build_scheduler(settings)
    assert scheduler.get_job("rotation") is not None
    scheduler.start()
    try:
        async with asyncio.timeout(30):
            rotated = await _finished_job(to_rotate["id"], "schedule")
            verified = await _finished_job(to_verify["id"], "verify")
    finally:
        scheduler.shutdown(wait=False)

    assert rotated["status"] == "succeeded"
    state = await rotlab.state(to_rotate["id"])
    assert state["secret_version"] == 2 and state["sync_status"] == "in_sync"
    assert rotlab.device.passwords[to_rotate["username"]] == await rotlab.current(to_rotate["id"])
    assert await rotlab.current(to_rotate["id"]) != START

    assert verified["status"] == "succeeded"
    vstate = await rotlab.state(to_verify["id"])
    assert vstate["secret_version"] == 1 and vstate["sync_status"] == "in_sync"
    # A verify changes nothing on the device.
    assert rotlab.device.passwords[to_verify["username"]] == START

    # Both were queued by the scheduler itself, and audited in their safe.
    queued = await sql(
        "SELECT details->>'reason' AS reason, safe_id FROM audit.events "
        "WHERE action = 'rotation.queued' AND details->>'account_id' IN (:a, :b)",
        a=to_rotate["id"],
        b=to_verify["id"],
    )
    assert sorted(q["reason"] for q in queued) == ["schedule", "verify"]
    assert all(str(q["safe_id"]) == safe_id for q in queued)


async def test_scheduler_queues_nothing_while_rotation_is_switched_off(rotlab):
    safe_id = await rotlab.safe(rotation_interval_days=1)
    account = await rotlab.account(safe_id=safe_id)
    await sql(
        "UPDATE inventory.accounts SET last_rotated_at = NOW() - INTERVAL '2 days' WHERE id = :a",
        a=account["id"],
    )
    settings = get_settings().model_copy(
        update={"rotation_enabled": False, "rotation_tick_seconds": 1, "rotation_jitter_seconds": 0}
    )
    scheduler = build_scheduler(settings)
    scheduler.start()
    try:
        await asyncio.sleep(3.5)  # several real ticks
    finally:
        scheduler.shutdown(wait=False)
    jobs = await sql("SELECT 1 FROM access.rotation_jobs WHERE account_id = :a", a=account["id"])
    assert jobs == []
    assert rotlab.driver.count("connect") == 0
