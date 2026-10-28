"""Crash and resume from every persisted state (ROTATION.md §5 recovery table).

A checkpoint kills the engine right after a state is committed (or, for
"device_answered", after the device accepted C but before WardX recorded it). The
lease then expires, as it would for a dead worker, and a fresh worker resumes the job.
"""

from __future__ import annotations

import pytest

from tests.integration.rotation.rotation_support import START, CrashAt, sql

pytestmark = pytest.mark.asyncio(loop_scope="session")

CRASH_POINTS = [
    "candidate_stored",  # C in the vault, device untouched
    "change_sent",  # change about to be sent (committed), not sent yet
    "device_answered",  # device accepted C, WardX did not record it
    "device_changed",
    "persisted",
]


@pytest.mark.parametrize("point", CRASH_POINTS)
async def test_crash_and_resume_from_every_state(rotlab, point):
    account = await rotlab.account()
    job = await rotlab.request(account["id"])
    crash = CrashAt(point)
    done = await rotlab.run(job["id"], crash)
    assert point in crash.seen
    assert done["status"] == "succeeded", (point, done)
    state = await rotlab.state(account["id"])
    assert state["secret_version"] == 2
    assert rotlab.device.passwords[account["username"]] == await rotlab.current(account["id"])
    # Nothing was ever deleted; C was the only candidate.
    assert await rotlab.labels(account["id"]) == {1: "previous", 2: "current"}


async def test_crash_after_claim_before_anything_restarts_cleanly(rotlab):
    account = await rotlab.account()
    job = await rotlab.request(account["id"])
    worker = rotlab.worker()
    assert await worker.claim() is not None  # claimed, then the process dies
    assert (await rotlab.job(job["id"]))["status"] == "running"
    await rotlab.expire_lease(job["id"])
    done = await rotlab.run(job["id"])
    assert done["status"] == "succeeded"
    assert done["attempts"] == 2


async def test_live_lease_is_never_stolen(rotlab):
    account = await rotlab.account()
    job = await rotlab.request(account["id"])
    assert await rotlab.worker().claim() is not None
    # Another worker sees nothing to do while the lease is live.
    assert await rotlab.worker().claim() is None
    await rotlab.expire_lease(job["id"])
    assert (await rotlab.run(job["id"]))["status"] == "succeeded"


async def test_one_running_job_per_target(rotlab):
    target = await rotlab.target()
    a = await rotlab.account(target=target)
    b = await rotlab.account(target=target)
    other = await rotlab.account()
    jobs = [await rotlab.request(x["id"]) for x in (a, b, other)]
    w1, w2, w3 = rotlab.worker(), rotlab.worker(), rotlab.worker()
    first = await w1.claim()
    second = await w2.claim()
    claimed = {str(first), str(second)}
    assert claimed <= {j["id"] for j in jobs}
    # The two on the shared target were not both claimed.
    assert not {jobs[0]["id"], jobs[1]["id"]} <= claimed
    assert await w3.claim() is None
    for j in jobs:
        await rotlab.expire_lease(j["id"])
        assert (await rotlab.run(j["id"]))["status"] == "succeeded"


async def test_resumed_device_changed_job_with_switch_off_needs_attention(rotlab):
    account = await rotlab.account()
    job = await rotlab.request(account["id"])
    await rotlab.run(job["id"], CrashAt("device_changed"), rounds=1)
    assert (await rotlab.job(job["id"]))["status"] == "device_changed"
    await rotlab.expire_lease(job["id"])
    await rotlab.tick(enabled=False)
    done = await rotlab.job(job["id"])
    # The device may hold C: never forget it, an administrator decides.
    assert done["status"] == "needs_attention"
    assert (await rotlab.labels(account["id"]))[2] == "candidate"


async def test_emergency_holder_appearing_mid_run_sends_the_job_back_to_wait(rotlab):
    account = await rotlab.account()
    job = await rotlab.request(account["id"])

    async def emergency():
        await sql(
            "INSERT INTO access.checkouts (account_id, user_id, reason, secret_version, "
            "expires_at, emergency) SELECT :a, id, 'break glass during rotation', 1, "
            "NOW() + INTERVAL '1 hour', TRUE FROM iam.users WHERE username = 'admin'",
            a=account["id"],
        )

    await rotlab.run(job["id"], CrashAt("candidate_stored", emergency), rounds=1)
    mid = await rotlab.job(job["id"])
    assert mid["status"] == "waiting_release"
    assert rotlab.driver.count("change") == 0
    assert rotlab.device.passwords[account["username"]] == START
    assert (await rotlab.labels(account["id"]))[2] == "abandoned"
    await sql(
        "UPDATE access.checkouts SET status = 'returned' WHERE account_id = :a", a=account["id"]
    )
    done = await rotlab.run(job["id"])
    assert done["status"] == "succeeded"
    assert (await rotlab.state(account["id"]))["secret_version"] == 3
