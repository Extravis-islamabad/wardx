"""The negative check in verify, and reviewing an untrustworthy verify (ROTATION.md §6).

A device that accepts any password proves nothing by a successful login, so every
verify ends with exactly one login using a fresh wrong password, which must be refused.
"""

from __future__ import annotations

import pytest

from src.core.config import get_settings
from src.core.context import Actor
from src.core.db import session_factory
from src.core.enums import Role
from src.dependencies.rotation import build_rotation_scheduler_service
from src.gateway.broker import Broker, GatewayDenied
from tests.integration.rotation.rotation_support import START, sql
from tests.integration.safes_support import me
from tests.integration.test_break_glass import REASON, make_holder

pytestmark = pytest.mark.asyncio(loop_scope="session")

GOOD_REASON = "Vendor confirmed PAM misconfig; fix scheduled CHG-1234"


@pytest.fixture
async def other_admin(make_user):
    """A second administrator, deactivated afterwards: test_access_flow (which runs later)
    expects the bootstrap admin to be the only active one."""
    from tests.integration.safes_support import tag

    name = f"conf{tag()}"
    headers = await make_user(name, role="admin")
    yield headers
    await sql("UPDATE iam.users SET is_active = FALSE WHERE username = :n", n=name)


def _wrong_attempts(rotlab, account_id_versions: list[str]) -> int:
    return sum(1 for s in rotlab.driver.verified if s not in account_id_versions)


async def _versions(rotlab, account) -> list[str]:
    from tests.integration.rotation.rotation_support import read_secret

    labels = await rotlab.labels(account["id"])
    return [await read_secret(account["id"], v) for v in labels]


async def _untrustworthy(rotlab) -> dict:
    """An account rotated on a device that accepts any password."""
    account = await rotlab.account()
    rotlab.device.accept_any = True
    done = await rotlab.run((await rotlab.request(account["id"]))["id"])
    rotlab.device.accept_any = False
    return {**account, "job": done}


async def _checkout(client, headers, account_id):
    return await client.post(
        "/checkouts",
        headers=headers,
        json={"account_id": account_id, "reason": "verify review", "duration_minutes": 5},
    )


async def test_wrong_password_accepted_promotes_but_marks_untrustworthy(rotlab):
    acc = await _untrustworthy(rotlab)
    done = acc["job"]
    assert done["status"] == "changed_unverified"
    assert done["verify_result"] == "untrustworthy"
    state = await rotlab.state(acc["id"])
    # The device holds the new password, so it is current; but it is not verified.
    assert state["secret_version"] == 2
    assert state["sync_status"] == "verify_untrustworthy"
    assert state["last_verified_at"] is None
    assert state["last_rotation_status"] == "changed_unverified"
    assert await rotlab.labels(acc["id"]) == {1: "previous", 2: "current"}
    assert "rotation.verify_untrustworthy" in await rotlab.alerts(acc["id"])
    assert _wrong_attempts(rotlab, await _versions(rotlab, acc)) == 1
    events = await sql(
        "SELECT action FROM audit.events WHERE details->>'account_id' = :a AND safe_id IS NULL",
        a=acc["id"],
    )
    assert events == []


async def test_untrustworthy_blocks_normal_access_but_not_break_glass(
    rotlab, client, admin, make_user
):
    acc = await _untrustworthy(rotlab)
    resp = await _checkout(client, admin, acc["id"])
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "verify_untrustworthy"

    admin_user = await me(client, admin)
    broker = Broker(get_settings(), "test-node")
    actor = Actor(id=admin_user["id"], username="admin", role=Role.ADMIN)
    with pytest.raises(GatewayDenied, match="untrustworthy"):
        await broker.open(
            actor,
            target_name=acc["target"]["name"],
            account_username=acc["username"],
            mode="shell",
            command=None,
        )

    holder = await make_holder(client, admin, make_user)
    resp = await client.post(
        f"/accounts/{acc['id']}/emergency-reveal",
        headers=holder["headers"],
        json={"reason": REASON},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["value"] == await rotlab.current(acc["id"])
    assert resp.json()["data"]["value"] != START


async def test_confirm_needs_a_real_reason_and_another_admin(rotlab, client, admin, other_admin):
    acc = await _untrustworthy(rotlab)
    url = f"/accounts/{acc['id']}/rotation/confirm"
    # The bootstrap admin requested the rotation: they may not confirm it.
    resp = await client.post(url, headers=admin, json={"reason": GOOD_REASON})
    assert resp.status_code == 403
    other = other_admin
    for body in ({}, {"reason": ""}, {"reason": "too short reason"}):
        resp = await client.post(url, headers=other, json=body)
        assert resp.status_code == 409, resp.text
        assert "20 characters" in resp.json()["error"]["message"]

    resp = await client.post(url, headers=other, json={"reason": GOOD_REASON})
    assert resp.status_code == 200, resp.text
    state = await rotlab.state(acc["id"])
    assert state["sync_status"] == "confirmed_untrustworthy"
    # Normal access works again.
    co = await _checkout(client, admin, acc["id"])
    assert co.status_code == 201, co.text
    await client.post(f"/checkouts/{co.json()['data']['id']}/checkin", headers=admin)
    # Listed on the dashboard with who, when and why.
    att = (await client.get("/rotation/attention", headers=admin)).json()["data"]
    entry = next(x for x in att["confirmed_untrustworthy"] if x["id"] == acc["id"])
    assert entry["risk_accepted_reason"] == GOOD_REASON
    assert entry["risk_accepted_by_name"]
    assert entry["risk_accepted_at"]
    alerts = await sql(
        "SELECT acknowledged_at FROM security.alerts WHERE object_id = :a "
        "AND kind = 'rotation.verify_untrustworthy'",
        a=acc["id"],
    )
    assert all(a["acknowledged_at"] is not None for a in alerts)

    # A later clean verify clears it from the dashboard (audited).
    done = await rotlab.run((await rotlab.request(acc["id"], "verify"))["id"])
    assert done["status"] == "succeeded", done
    assert (await rotlab.state(acc["id"]))["sync_status"] == "in_sync"
    att = (await client.get("/rotation/attention", headers=admin)).json()["data"]
    assert acc["id"] not in [x["id"] for x in att["confirmed_untrustworthy"]]
    cleared = await sql(
        "SELECT safe_id FROM audit.events WHERE action = 'rotation.accepted_risk_cleared' "
        "AND object_id = :a",
        a=acc["id"],
    )
    assert len(cleared) == 1 and cleared[0]["safe_id"] is not None


async def test_confirmed_account_accepting_a_wrong_password_again_is_blocked_again(
    rotlab, client, admin, other_admin
):
    acc = await _untrustworthy(rotlab)
    other = other_admin
    resp = await client.post(
        f"/accounts/{acc['id']}/rotation/confirm", headers=other, json={"reason": GOOD_REASON}
    )
    assert resp.status_code == 200, resp.text
    before = len(await rotlab.alerts(acc["id"]))
    rotlab.device.accept_any = True
    done = await rotlab.run((await rotlab.request(acc["id"], "verify"))["id"])
    rotlab.device.accept_any = False
    assert done["status"] == "failed"
    assert (await rotlab.state(acc["id"]))["sync_status"] == "verify_untrustworthy"
    assert (await _checkout(client, admin, acc["id"])).status_code == 409
    kinds = await rotlab.alerts(acc["id"])
    assert len(kinds) == before + 1 and kinds[-1] == "rotation.verify_untrustworthy"


async def test_reconcile_clears_untrustworthy_only_after_a_clean_verify(rotlab, client, admin):
    target = await rotlab.target()
    rec = await rotlab.account(target=target, password="Reconcile-Admin-Pw-1")
    acc = await rotlab.account(target=target)
    await client.patch(
        f"/accounts/{acc['id']}", headers=admin, json={"reconcile_account_id": rec["id"]}
    )
    rotlab.device.accept_any = True
    await rotlab.run((await rotlab.request(acc["id"]))["id"])
    assert (await rotlab.state(acc["id"]))["sync_status"] == "verify_untrustworthy"
    # Reconcile while the device still accepts anything: still untrustworthy.
    done = await rotlab.run((await rotlab.request(acc["id"], "reconcile"))["id"])
    assert done["verify_result"] == "untrustworthy"
    assert (await rotlab.state(acc["id"]))["sync_status"] == "verify_untrustworthy"
    # The device is fixed; a reconcile ending in a clean verify clears it.
    rotlab.device.accept_any = False
    done = await rotlab.run((await rotlab.request(acc["id"], "reconcile"))["id"])
    assert done["status"] == "succeeded", done
    assert (await rotlab.state(acc["id"]))["sync_status"] == "in_sync"
    assert (await _checkout(client, admin, acc["id"])).status_code == 201


async def test_inconclusive_negative_check_waits_for_the_schedule(rotlab):
    account = await rotlab.account()
    rotlab.driver.fail("verify", None, "unreachable")  # positive ok, the wrong one times out
    done = await rotlab.run((await rotlab.request(account["id"]))["id"])
    assert done["status"] == "changed_unverified"
    assert done["verify_result"] == "inconclusive"
    state = await rotlab.state(account["id"])
    assert state["sync_status"] == "unverified" and state["secret_version"] == 2
    assert _wrong_attempts(rotlab, await _versions(rotlab, account)) == 1

    async def enqueue() -> None:
        async with session_factory()() as s:
            await build_rotation_scheduler_service(s).enqueue_due(enabled=True, jitter_seconds=0)
        # Only this test's account matters here.
        await sql(
            "UPDATE access.rotation_jobs SET status = 'cancelled' "
            "WHERE status = 'pending' AND account_id <> :a",
            a=account["id"],
        )

    # Not immediately: no second wrong-password attempt right after.
    await enqueue()
    assert await rotlab.tick() == 0
    assert _wrong_attempts(rotlab, await _versions(rotlab, account)) == 1
    # On schedule: the positive login and one new wrong attempt.
    await sql(
        "UPDATE inventory.accounts SET last_verify_attempt_at = NOW() - INTERVAL '25 hours' "
        "WHERE id = :a",
        a=account["id"],
    )
    await enqueue()
    job = await one_job(account["id"], "verify")
    done = await rotlab.run(job)
    assert done["status"] == "succeeded"
    assert (await rotlab.state(account["id"]))["sync_status"] == "in_sync"
    assert _wrong_attempts(rotlab, await _versions(rotlab, account)) == 2


async def one_job(account_id: str, reason: str) -> str:
    rows = await sql(
        "SELECT id FROM access.rotation_jobs WHERE account_id = :a AND reason = :r "
        "AND status = 'pending'",
        a=account_id,
        r=reason,
    )
    assert len(rows) == 1
    return str(rows[0]["id"])
