"""Break-glass while a rotation needs attention (ROTATION.md §14, fix 5).

Normal access is blocked, break-glass still works and reveals the account's
current version (never the unpromoted candidate), with a notice naming the
candidate the device may hold instead.
"""

from __future__ import annotations

import pytest

from tests.integration.rotation.rotation_support import START, CrashAt, sql
from tests.integration.test_break_glass import REASON, make_holder

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _needs_attention(rotlab) -> tuple[dict, dict]:
    """A job stuck after the device took the candidate: the device holds C, the vault's
    current version is still N."""
    account = await rotlab.account()
    job = await rotlab.request(account["id"])
    await rotlab.run(job["id"], CrashAt("device_changed"), rounds=1)
    await rotlab.expire_lease(job["id"])
    await rotlab.tick(enabled=False)
    done = await rotlab.job(job["id"])
    assert done["status"] == "needs_attention", done
    return account, done


async def test_break_glass_reveals_the_current_version_with_a_notice(
    rotlab, client, admin, make_user
):
    account, job = await _needs_attention(rotlab)
    state = await rotlab.state(account["id"])
    assert state["secret_version"] == 1
    assert (await rotlab.labels(account["id"]))[2] == "candidate"

    # Normal access is blocked while the job needs attention.
    resp = await client.post(
        "/checkouts",
        headers=admin,
        json={"account_id": account["id"], "reason": "normal access attempt"},
    )
    assert resp.status_code == 409, resp.text

    holder = await make_holder(client, admin, make_user)
    resp = await client.post(
        f"/accounts/{account['id']}/emergency-reveal",
        headers=holder["headers"],
        json={"reason": REASON},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    # The current version (N), never the unpromoted candidate (C).
    assert data["value"] == START == await rotlab.current(account["id"])
    candidate = rotlab.device.passwords[account["username"]]
    assert candidate != START and data["value"] != candidate
    notice = data["notice"]
    assert notice and "needs attention" in notice
    assert "v1" in notice and f"v{job['candidate_version']}" in notice
    assert candidate not in notice

    # Audited and alerted like every break-glass use, in the account's safe.
    safe_id = (await sql("SELECT safe_id FROM inventory.accounts WHERE id = :a", a=account["id"]))[
        0
    ]["safe_id"]
    events = await sql(
        "SELECT safe_id FROM audit.events WHERE action = 'secret.emergency_reveal' "
        "AND details->>'account_id' = :a",
        a=account["id"],
    )
    assert len(events) == 1 and events[0]["safe_id"] == safe_id
    alerts = await sql(
        "SELECT severity FROM security.alerts WHERE kind = 'break_glass.used' AND object_id = :a",
        a=account["id"],
    )
    assert [a["severity"] for a in alerts] == ["high"]


async def test_break_glass_has_no_notice_when_rotation_is_healthy(rotlab, client, admin, make_user):
    account = await rotlab.account()
    holder = await make_holder(client, admin, make_user)
    resp = await client.post(
        f"/accounts/{account['id']}/emergency-reveal",
        headers=holder["headers"],
        json={"reason": REASON},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["notice"] is None
    assert resp.json()["data"]["value"] == START
