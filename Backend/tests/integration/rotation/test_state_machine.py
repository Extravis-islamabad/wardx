"""The rotation state machine with a failure injected at every step (ROTATION.md §5).

A simulated device (fake_driver.py) stands in for the platform; the database, vault,
audit and alerts are real. After every scenario the invariant holds: the vault's
current version is a password the device accepts (or the job needs attention), and
no version is ever deleted.
"""

from __future__ import annotations

import pytest

from src.services.rotation.rotation_store import RotationStore
from tests.integration.rotation.fake_driver import FakeDriver
from tests.integration.rotation.rotation_support import START, CrashAt, sql

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _assert_in_step(rotlab, account: dict) -> None:
    """The vault's current password is the one on the device."""
    assert rotlab.device.passwords[account["username"]] == await rotlab.current(account["id"])


async def test_happy_path_promotes_after_a_clean_verify(rotlab):
    account = await rotlab.account()
    job = await rotlab.request(account["id"])
    assert job["status"] == "pending"

    done = await rotlab.run(job["id"])
    assert done["status"] == "succeeded", done
    assert done["verify_result"] == "verified"
    state = await rotlab.state(account["id"])
    assert state["secret_version"] == 2
    assert state["sync_status"] == "in_sync"
    assert state["last_verified_at"] is not None
    await _assert_in_step(rotlab, account)
    assert await rotlab.labels(account["id"]) == {1: "previous", 2: "current"}
    steps = [s["step"] for s in done["steps"]]
    assert steps == ["store_candidate", "change", "persist", "verify", "verify_negative"]
    # Exactly one wrong-password attempt, refused.
    new = await rotlab.current(account["id"])
    wrong = [s for s in rotlab.driver.verified if s not in (new, START)]
    assert len(wrong) == 1
    assert done["steps"][-1]["outcome"] == "auth_failed"
    # No secret in any stored transcript or detail.
    for s in done["steps"]:
        for field in (s["transcript"] or "", s["detail"] or ""):
            assert new not in field and START not in field


async def test_vault_write_failure_never_touches_the_device(rotlab, monkeypatch):
    async def broken(self, ctx, secret, driver):
        raise RuntimeError("vault down")

    monkeypatch.setattr(RotationStore, "store_candidate", broken)
    account = await rotlab.account()
    job = await rotlab.request(account["id"])
    done = await rotlab.run(job["id"])
    assert done["status"] == "failed"
    assert "vault" in done["detail"].lower()
    assert rotlab.driver.calls == []
    assert rotlab.device.passwords[account["username"]] == START
    assert (await rotlab.state(account["id"]))["secret_version"] == 1


async def test_unreachable_backs_off_then_fails_with_candidate_abandoned(rotlab):
    account = await rotlab.account()
    rotlab.driver.fail("connect", "unreachable", "unreachable", "unreachable")
    job = await rotlab.request(account["id"])
    await rotlab.tick()
    first = await rotlab.job(job["id"])
    assert first["status"] == "candidate_stored"
    assert first["attempts"] == 1
    # Backed off: not due again yet.
    assert await rotlab.tick() == 0
    done = await rotlab.run(job["id"])
    assert done["status"] == "failed"
    assert done["attempts"] == 3
    assert rotlab.device.passwords[account["username"]] == START
    assert (await rotlab.state(account["id"]))["secret_version"] == 1
    assert (await rotlab.labels(account["id"]))[2] == "abandoned"


async def test_current_password_rejected_marks_out_of_sync(rotlab):
    account = await rotlab.account()
    rotlab.device.passwords[account["username"]] = "Changed-Behind-Our-Back-1"
    job = await rotlab.request(account["id"])
    done = await rotlab.run(job["id"])
    assert done["status"] == "failed"
    state = await rotlab.state(account["id"])
    assert state["sync_status"] == "out_of_sync"
    assert state["secret_version"] == 1
    assert (await rotlab.labels(account["id"]))[2] == "abandoned"
    assert "rotation.out_of_sync" in await rotlab.alerts(account["id"])


async def test_host_key_mismatch_refuses_and_alerts(rotlab):
    account = await rotlab.account()
    rotlab.driver.fail("connect", "host_key")
    done = await rotlab.run((await rotlab.request(account["id"]))["id"])
    assert done["status"] == "failed"
    assert rotlab.driver.count("change") == 0
    assert "rotation.host_key_mismatch" in await rotlab.alerts(account["id"])


async def test_device_rejects_the_candidate(rotlab):
    account = await rotlab.account()
    rotlab.driver.fail("change", "rejected")
    done = await rotlab.run((await rotlab.request(account["id"]))["id"])
    assert done["status"] == "failed"
    assert "refused" in done["detail"]
    assert rotlab.device.passwords[account["username"]] == START
    await _assert_in_step(rotlab, account)


async def test_ambiguous_change_that_applied_is_promoted(rotlab):
    account = await rotlab.account()
    rotlab.driver.fail("change", "ambiguous_applied")
    done = await rotlab.run((await rotlab.request(account["id"]))["id"])
    assert done["status"] == "succeeded", done
    assert "recover_verify_candidate" in [s["step"] for s in done["steps"]]
    await _assert_in_step(rotlab, account)


async def test_ambiguous_change_that_was_lost_is_retried(rotlab):
    account = await rotlab.account()
    rotlab.driver.fail("change", "ambiguous_lost")
    done = await rotlab.run((await rotlab.request(account["id"]))["id"])
    assert done["status"] == "succeeded", done
    steps = [s["step"] for s in done["steps"]]
    assert "recover_verify_current" in steps
    assert rotlab.driver.count("change") == 2
    await _assert_in_step(rotlab, account)


async def test_save_fails_twice_rolls_back_to_the_current_password(rotlab):
    account = await rotlab.account()
    rotlab.driver.fail("persist", "fail", "fail")
    done = await rotlab.run((await rotlab.request(account["id"]))["id"])
    assert done["status"] == "failed", done
    assert "rolled back" in done["detail"]
    assert rotlab.device.passwords[account["username"]] == START
    await _assert_in_step(rotlab, account)
    assert (await rotlab.labels(account["id"]))[2] == "abandoned"


async def test_save_fails_once_is_retried(rotlab):
    account = await rotlab.account()
    rotlab.driver.fail("persist", "fail")
    done = await rotlab.run((await rotlab.request(account["id"]))["id"])
    assert done["status"] == "succeeded"
    assert rotlab.driver.count("persist") == 2


async def test_failed_rollback_needs_attention(rotlab):
    account = await rotlab.account()
    rotlab.driver.fail("persist", "fail", "fail")
    rotlab.driver.fail("change", None, "rejected")  # the change works, the rollback does not
    done = await rotlab.run((await rotlab.request(account["id"]))["id"])
    assert done["status"] == "needs_attention", done
    assert (await rotlab.state(account["id"]))["rotation_status"] == "needs_attention"
    assert "rotation.needs_attention" in await rotlab.alerts(account["id"])
    # Both versions kept.
    assert set(await rotlab.labels(account["id"])) == {1, 2}


async def test_device_did_not_keep_the_change_is_retried(rotlab):
    account = await rotlab.account()
    user = account["username"]

    async def revert():  # e.g. a reboot reverted the change before the verify
        rotlab.device.passwords[user] = START

    done = await rotlab.run(
        (await rotlab.request(account["id"]))["id"], CrashAt("persisted", revert)
    )
    assert done["status"] == "succeeded", done
    assert "verify_current" in [s["step"] for s in done["steps"]]
    await _assert_in_step(rotlab, account)


async def test_neither_password_works_needs_attention_and_resolves(rotlab, admin, client):
    account = await rotlab.account()
    user = account["username"]

    async def scramble():
        rotlab.device.passwords[user] = "Something-Else-Entirely-9"

    job = await rotlab.request(account["id"])
    done = await rotlab.run(job["id"], CrashAt("persisted", scramble))
    assert done["status"] == "needs_attention"
    # Automatic retries stop: another tick does nothing.
    await rotlab.due_now(job["id"])
    assert await rotlab.tick() == 0
    # Normal check-outs are blocked meanwhile.
    resp = await client.post(
        "/checkouts",
        headers=admin,
        json={"account_id": account["id"], "reason": "need it", "duration_minutes": 5},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "rotation_pending"
    # Resolve by setting what is on the device now.
    resp = await client.post(
        f"/rotation/jobs/{job['id']}/resolve",
        headers=admin,
        json={
            "action": "set_secret",
            "note": "reset by hand",
            "secret": "Something-Else-Entirely-9",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "resolved"
    await _assert_in_step(rotlab, account)
    assert "rotation.resolve" in [
        r["action"]
        for r in await sql(
            "SELECT action FROM audit.events WHERE object_id = :i AND safe_id IS NOT NULL",
            i=job["id"],
        )
    ]


async def test_verify_unreachable_reschedules_in_persisted(rotlab):
    account = await rotlab.account()
    rotlab.driver.fail("verify", "unreachable")
    job = await rotlab.request(account["id"])
    await rotlab.tick()
    mid = await rotlab.job(job["id"])
    assert mid["status"] == "persisted"
    done = await rotlab.run(job["id"])
    assert done["status"] == "succeeded"
    await _assert_in_step(rotlab, account)


async def test_change_through_a_reconcile_account(rotlab):
    driver = FakeDriver(rotlab.device, persist=False, self_change=False)
    rotlab.use(driver)
    target = await rotlab.target()
    admin_acc = await rotlab.account(target=target, password="Reconcile-Admin-Pw-1")
    account = await rotlab.account(target=target)
    resp = await rotlab.client.patch(
        f"/accounts/{account['id']}",
        headers=rotlab.admin,
        json={"reconcile_account_id": admin_acc["id"]},
    )
    assert resp.status_code == 200, resp.text
    done = await rotlab.run((await rotlab.request(account["id"]))["id"])
    assert done["status"] == "succeeded", done
    assert driver.count("reconcile") == 1 and driver.count("change") == 0
    assert driver.calls[0] == ("connect", admin_acc["username"])
    await _assert_in_step(rotlab, account)
