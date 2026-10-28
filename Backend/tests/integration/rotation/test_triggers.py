"""Triggers (after use, scheduled, on demand), waiting for release, and the safety switches.

ROTATION.md §1 (switches, Telnet), §4 (triggers, holders and waiting).
"""

from __future__ import annotations

import pytest

from src.core.config import get_settings
from src.core.db import session_factory
from src.dependencies.rotation import build_rotation_scheduler_service
from tests.integration.approvals_support import sweep
from tests.integration.rotation.rotation_support import START, sql
from tests.integration.test_break_glass import REASON, make_holder

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _checkout(client, headers, account_id):
    return await client.post(
        "/checkouts",
        headers=headers,
        json={"account_id": account_id, "reason": "trigger test", "duration_minutes": 5},
    )


async def _open_job(account_id: str) -> dict | None:
    rows = await sql(
        "SELECT id, status, reason FROM access.rotation_jobs WHERE account_id = :a "
        "AND status NOT IN ('succeeded','failed','cancelled','resolved','changed_unverified')",
        a=account_id,
    )
    return dict(rows[0]) if rows else None


async def test_after_use_waits_for_an_emergency_holder(rotlab, client, admin, make_user):
    safe_id = await rotlab.safe(rotate_after_use=True, max_release_wait_minutes=5)
    account = await rotlab.account(safe_id=safe_id)
    co = (await _checkout(client, admin, account["id"])).json()["data"]
    assert await _open_job(account["id"]) is None  # nothing while held
    holder = await make_holder(client, admin, make_user)
    resp = await client.post(
        f"/accounts/{account['id']}/emergency-reveal",
        headers=holder["headers"],
        json={"reason": REASON},
    )
    assert resp.status_code == 200
    await client.post(f"/checkouts/{co['id']}/checkin", headers=admin)
    job = await _open_job(account["id"])
    assert job["status"] == "waiting_release" and job["reason"] == "after_use"
    # New normal check-outs wait; emergency ones do not (they extend the wait).
    resp = await _checkout(client, admin, account["id"])
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "rotation_pending"
    await rotlab.tick()
    assert (await _open_job(account["id"]))["status"] == "waiting_release"
    assert rotlab.driver.calls == []
    # Past max_release_wait: one high alert, and it keeps waiting.
    await sql(
        "UPDATE access.rotation_jobs SET waiting_since = NOW() - INTERVAL '10 minutes' "
        "WHERE id = :j",
        j=job["id"],
    )
    await rotlab.tick()
    await rotlab.tick()
    assert (await rotlab.alerts(account["id"])).count("rotation.release_wait_exceeded") == 1
    att = (await client.get("/rotation/attention", headers=admin)).json()["data"]
    assert str(job["id"]) in [j["id"] for j in att["release_overdue"]]
    assert rotlab.device.passwords[account["username"]] == START
    # The emergency holder checks in: now it rotates.
    emergency = resp_id = (
        await sql(
            "SELECT id FROM access.checkouts WHERE account_id = :a AND status = 'active'",
            a=account["id"],
        )
    )[0]["id"]
    assert emergency == resp_id
    resp = await client.post(f"/checkouts/{emergency}/checkin", headers=holder["headers"])
    assert resp.status_code == 200, resp.text
    done = await rotlab.run(str(job["id"]))
    assert done["status"] == "succeeded", done
    assert rotlab.device.passwords[account["username"]] == await rotlab.current(account["id"])


async def test_live_gateway_session_is_a_holder(rotlab, client, admin):
    account = await rotlab.account()
    await sql(
        "INSERT INTO access.sessions (user_id, account_id, account_username, target_name, "
        "target_address, protocol, status) SELECT id, :a, 'u', 't', 'x', 'ssh', 'active' "
        "FROM iam.users WHERE username = 'admin'",
        a=account["id"],
    )
    job = await rotlab.request(account["id"])
    await rotlab.tick()
    assert (await rotlab.job(job["id"]))["status"] == "waiting_release"
    await sql("UPDATE access.sessions SET status = 'closed' WHERE account_id = :a", a=account["id"])
    assert (await rotlab.run(job["id"]))["status"] == "succeeded"


async def test_expiry_triggers_after_use(rotlab, client, admin):
    safe_id = await rotlab.safe(rotate_after_use=True)
    account = await rotlab.account(safe_id=safe_id)
    co = (await _checkout(client, admin, account["id"])).json()["data"]
    await sql(
        "UPDATE access.checkouts SET expires_at = NOW() - INTERVAL '1 second' WHERE id = :c",
        c=co["id"],
    )
    await sweep()
    job = await _open_job(account["id"])
    assert job["reason"] == "after_use"
    assert (await rotlab.run(str(job["id"])))["status"] == "succeeded"


async def test_scheduled_rotation_respects_the_maintenance_window(rotlab, client, admin):
    safe_id = await rotlab.safe()
    account = await rotlab.account(safe_id=safe_id)
    await sql(
        "UPDATE inventory.accounts SET rotation_interval_days = 1, last_rotated_at = "
        "NOW() - INTERVAL '2 days', last_verify_attempt_at = NOW() WHERE id = :a",
        a=account["id"],
    )

    async def enqueue():
        async with session_factory()() as s:
            await build_rotation_scheduler_service(s).enqueue_due(enabled=True, jitter_seconds=0)
        await sql(
            "UPDATE access.rotation_jobs SET status = 'cancelled' "
            "WHERE status = 'pending' AND account_id <> :a",
            a=account["id"],
        )

    # A window that never contains now: no job.
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    other_day = (now.weekday() + 3) % 7
    resp = await client.put(
        f"/safes/{safe_id}/rotation-policy",
        headers=admin,
        json={"maintenance_window": {"days": [other_day], "start_hour": 0, "end_hour": 24}},
    )
    assert resp.status_code == 200, resp.text
    await enqueue()
    assert await _open_job(account["id"]) is None
    await client.put(f"/safes/{safe_id}/rotation-policy", headers=admin, json={})
    await enqueue()
    job = await _open_job(account["id"])
    assert job["reason"] == "schedule"
    assert (await rotlab.run(str(job["id"])))["status"] == "succeeded"


async def test_switches_off_mean_no_connection_at_all(rotlab, client, admin):
    account = await rotlab.account()
    settings = get_settings()
    settings.rotation_enabled = False
    try:
        resp = await client.post(
            f"/accounts/{account['id']}/rotate", headers=admin, json={"reason": "switch off"}
        )
        assert resp.status_code == 409
        assert "switched off" in resp.json()["error"]["message"]
        async with session_factory()() as s:
            out = await build_rotation_scheduler_service(s).enqueue_due(enabled=False)
        assert out == {"rotations": 0, "verifies": 0}
    finally:
        settings.rotation_enabled = True
    # Queued while on, then the engine runs with the switch off: refused, nothing sent.
    job = await rotlab.request(account["id"])
    await rotlab.tick(enabled=False)
    done = await rotlab.job(job["id"])
    assert done["status"] == "failed" and "switched off" in done["detail"]
    # The target switch.
    blocked = await rotlab.account(target=await rotlab.target(allowed=False))
    resp = await client.post(
        f"/accounts/{blocked['id']}/verify", headers=admin, json={"reason": "target off"}
    )
    assert resp.status_code == 409 and "not allowed" in resp.json()["error"]["message"]
    job = await rotlab.request(account["id"])
    await client.patch(
        f"/targets/{account['target']['id']}", headers=admin, json={"rotation_allowed": False}
    )
    await rotlab.tick()
    assert (await rotlab.job(job["id"]))["status"] == "failed"
    assert rotlab.driver.calls == []
    assert rotlab.device.passwords[account["username"]] == START


async def test_telnet_targets_are_non_rotatable(rotlab, client, admin):
    target = await rotlab.target(protocol="telnet")
    assert target["non_rotatable_reason"] == "non-rotatable (Telnet)"
    account = await rotlab.account(target=target)
    resp = await client.post(
        f"/accounts/{account['id']}/rotate", headers=admin, json={"reason": "telnet"}
    )
    assert resp.status_code == 409
    assert "non-rotatable (Telnet)" in resp.json()["error"]["message"]


async def test_dry_run_changes_nothing(rotlab):
    account = await rotlab.account()
    done = await rotlab.run((await rotlab.request(account["id"], dry_run=True))["id"])
    assert done["status"] == "succeeded" and done["detail"] == "dry run: nothing changed"
    assert rotlab.driver.count("change") == 0
    state = await rotlab.state(account["id"])
    assert state["secret_version"] == 1 and state["sync_status"] == "in_sync"


async def test_verify_out_of_sync_alerts_and_auto_reconciles_when_on(rotlab, client, admin):
    safe_id = await rotlab.safe()
    await client.put(
        f"/safes/{safe_id}/rotation-policy", headers=admin, json={"auto_reconcile": True}
    )
    target = await rotlab.target()
    rec = await rotlab.account(target=target, safe_id=safe_id, password="Reconcile-Admin-Pw-1")
    account = await rotlab.account(target=target, safe_id=safe_id)
    await client.patch(
        f"/accounts/{account['id']}", headers=admin, json={"reconcile_account_id": rec["id"]}
    )
    rotlab.device.passwords[account["username"]] = "Changed-Behind-Our-Back-2"
    done = await rotlab.run((await rotlab.request(account["id"], "verify"))["id"])
    assert done["status"] == "failed"
    assert (await rotlab.state(account["id"]))["sync_status"] == "out_of_sync"
    assert "rotation.out_of_sync" in await rotlab.alerts(account["id"])
    job = await _open_job(account["id"])
    assert job["reason"] == "reconcile"
    assert (await rotlab.run(str(job["id"])))["status"] == "succeeded"
    assert (await rotlab.state(account["id"]))["sync_status"] == "in_sync"
    assert rotlab.device.passwords[account["username"]] == await rotlab.current(account["id"])
