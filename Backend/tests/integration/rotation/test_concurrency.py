"""One account, one rotation at a time (ROTATION.md §14, fix 1).

The per-account advisory lock is held for a whole run, so a second worker never
works on the same account, even when it legitimately claims the job because the
first run's lease ran out while that run was still busy on the device.
"""

from __future__ import annotations

import asyncio

import pytest

from tests.integration.rotation.fake_driver import FakeDriver
from tests.integration.rotation.rotation_support import START

pytestmark = pytest.mark.asyncio(loop_scope="session")


class GatedDriver(FakeDriver):
    """Holds every change until the test opens the gate, so two runs really overlap."""

    def __init__(self, device) -> None:
        super().__init__(device)
        self.entered = asyncio.Event()
        self.gate = asyncio.Event()

    async def change(self, session, account, current, new, ctx):
        self.entered.set()
        await self.gate.wait()
        return await super().change(session, account, current, new, ctx)


async def _second_run_is_refused(rotlab, job_id: str, second) -> None:
    """While the first run is held mid-change, the second does nothing to the device."""
    changes_before = rotlab.driver.count("change")
    connects_before = rotlab.driver.count("connect")
    assert await second() is False
    assert rotlab.driver.count("change") == changes_before
    assert rotlab.driver.count("connect") == connects_before


async def test_two_runs_of_the_same_job_never_overlap(rotlab):
    rotlab.use(GatedDriver(rotlab.device))
    account = await rotlab.account()
    job = await rotlab.request(account["id"])
    await rotlab.due_now(job["id"])

    first_worker = rotlab.worker()
    first = asyncio.create_task(first_worker.run_once())
    await asyncio.wait_for(rotlab.driver.entered.wait(), 10)

    # A second engine driving the same job directly: refused by the account lock.
    await _second_run_is_refused(rotlab, job["id"], lambda: rotlab.worker().engine.run(job["id"]))

    rotlab.driver.gate.set()
    assert await asyncio.wait_for(first, 30) == 1
    done = await rotlab.job(job["id"])
    assert done["status"] == "succeeded", done
    state = await rotlab.state(account["id"])
    assert state["secret_version"] == 2
    assert await rotlab.labels(account["id"]) == {1: "previous", 2: "current"}
    assert rotlab.device.passwords[account["username"]] == await rotlab.current(account["id"])
    assert rotlab.driver.count("change") == 1


async def test_expired_lease_reclaim_does_not_run_alongside_the_slow_run(rotlab):
    """The case the lock exists for: the lease runs out while the first run is still on
    the device, a second worker claims the job, and must still not touch the account."""
    rotlab.use(GatedDriver(rotlab.device))
    account = await rotlab.account()
    job = await rotlab.request(account["id"])
    await rotlab.due_now(job["id"])

    first = asyncio.create_task(rotlab.worker().run_once())
    await asyncio.wait_for(rotlab.driver.entered.wait(), 10)
    await rotlab.expire_lease(job["id"])

    second_worker = rotlab.worker()
    assert await second_worker.claim() is not None  # the lease really is claimable
    await _second_run_is_refused(rotlab, job["id"], lambda: second_worker.engine.run(job["id"]))

    rotlab.driver.gate.set()
    await asyncio.wait_for(first, 30)
    done = await rotlab.job(job["id"])
    assert done["status"] == "succeeded", done
    # Exactly one candidate, promoted once; the device and the vault agree.
    assert await rotlab.labels(account["id"]) == {1: "previous", 2: "current"}
    assert rotlab.device.passwords[account["username"]] == await rotlab.current(account["id"])
    assert rotlab.driver.count("change") == 1


async def test_a_finished_job_is_not_run_again(rotlab):
    account = await rotlab.account()
    job = await rotlab.request(account["id"])
    done = await rotlab.run(job["id"])
    assert done["status"] == "succeeded"
    changes = rotlab.driver.count("change")
    # Re-running the finished job takes the lock, sees a final state and does nothing.
    assert await rotlab.worker().engine.run(job["id"]) is True
    assert rotlab.driver.count("change") == changes
    assert (await rotlab.state(account["id"]))["secret_version"] == 2
    assert await rotlab.current(account["id"]) != START


async def test_verify_cannot_start_while_a_rotation_is_open(rotlab):
    """Verify and rotate of one account never overlap: one open job per account, and the
    lock covers any run that gets past that."""
    rotlab.use(GatedDriver(rotlab.device))
    account = await rotlab.account()
    job = await rotlab.request(account["id"])
    await rotlab.due_now(job["id"])
    first = asyncio.create_task(rotlab.worker().run_once())
    await asyncio.wait_for(rotlab.driver.entered.wait(), 10)

    resp = await rotlab.client.post(
        f"/accounts/{account['id']}/verify",
        headers=rotlab.admin,
        json={"reason": "rotation test"},
    )
    assert resp.status_code == 409, resp.text

    rotlab.driver.gate.set()
    await asyncio.wait_for(first, 30)
    assert (await rotlab.job(job["id"]))["status"] == "succeeded"
