"""End to end against the MikroTik CHR lab (ROTATION.md §9, §15), like test_linux_e2e.py:

identity pinned through the Host key flow → two-level approval → check-out → check-in →
rotate-after-use waiting for an emergency holder → rotation over API-SSL → verify.
Skipped, with the reason, when the CHR is not available.
"""

from __future__ import annotations

import pytest

from src.core.config import get_settings
from tests.integration.approvals_support import (
    APPROVER_PERMS,
    REQUESTER_PERMS,
    decide,
    person,
    request_access,
)
from tests.integration.rotation.mikrotik_lab import Chr, requires_chr
from tests.integration.rotation.test_mikrotik_lab import ChrLab
from tests.integration.test_break_glass import REASON, make_holder

pytestmark = [pytest.mark.asyncio(loop_scope="session"), requires_chr]


@pytest.fixture(scope="module")
async def chr_box():
    box = await Chr.connect()
    try:
        yield box
    finally:
        try:
            await box.remove_all()
            await box.check_restored()
        finally:
            await box.close()


@pytest.fixture
async def chr_lab(client, admin, chr_box):
    settings = get_settings()
    settings.rotation_enabled = True
    yield ChrLab(client, admin, chr_box)
    settings.rotation_enabled = False


async def test_approval_checkout_checkin_rotate_after_use_verify(
    chr_lab, chr_box, client, admin, make_user
):
    safe_id = await chr_lab.safe(rotate_after_use=True)
    resp = await client.put(
        f"/safes/{safe_id}/policy",
        headers=admin,
        json={
            "approval_required": True,
            "levels": [{"required_approvals": 1}, {"required_approvals": 1}],
        },
    )
    assert resp.status_code == 200, resp.text
    requester = await person(client, make_user, admin, safe_id, REQUESTER_PERMS)
    first = await person(client, make_user, admin, safe_id, APPROVER_PERMS)
    second = await person(client, make_user, admin, safe_id, APPROVER_PERMS)
    account = await chr_lab.chr_account("e2e", safe_id=safe_id)
    user, original = account["username"], account["device_password"]
    rotation = (await client.get(f"/accounts/{account['id']}/rotation", headers=admin)).json()
    assert rotation["data"]["identity_blocker"] is None  # both identities pinned

    # Two-level approval.
    req = (await request_access(client, requester["headers"], account["id"])).json()["data"]
    after1 = (await decide(client, first["headers"], req["id"])).json()["data"]
    assert (after1["status"], after1["current_level"]) == ("pending", 2)
    after2 = (await decide(client, second["headers"], req["id"])).json()["data"]
    assert after2["status"] == "approved"

    # Check-out and reveal: the requester gets the working password.
    co = await client.post(
        "/checkouts",
        headers=requester["headers"],
        json={"account_id": account["id"], "request_id": req["id"]},
    )
    assert co.status_code == 201, co.text
    co = co.json()["data"]
    shown = await client.post(f"/checkouts/{co['id']}/reveal", headers=requester["headers"])
    assert shown.json()["data"]["value"] == original
    assert await chr_box.login_works(user, original)

    # An emergency holder takes it too.
    holder = await make_holder(client, admin, make_user)
    bg = await client.post(
        f"/accounts/{account['id']}/emergency-reveal",
        headers=holder["headers"],
        json={"reason": REASON},
    )
    assert bg.status_code == 200, bg.text

    # Check-in: rotate-after-use is queued and waits for the emergency holder.
    assert (
        await client.post(f"/checkouts/{co['id']}/checkin", headers=requester["headers"])
    ).status_code == 200
    rotation = (await client.get(f"/accounts/{account['id']}/rotation", headers=admin)).json()
    job = rotation["data"]["open_job"]
    assert job["status"] == "waiting_release" and job["reason"] == "after_use"
    await chr_lab.tick()
    assert (await chr_lab.job(job["id"]))["status"] == "waiting_release"
    assert await chr_box.login_works(user, original)  # never rotated under a holder

    # The emergency holder checks in: the rotation runs over API-SSL and verifies.
    await client.post(
        f"/checkouts/{bg.json()['data']['checkout_id']}/checkin", headers=holder["headers"]
    )
    done = await chr_lab.run(job["id"])
    assert done["status"] == "succeeded", done
    assert done["verify_result"] == "verified"
    assert {s["channel"] for s in done["steps"] if s["channel"]} == {"api-ssl"}
    new = await chr_lab.current(account["id"])
    assert new != original
    assert await chr_box.login_works(user, new)
    assert not await chr_box.login_works(user, original)

    # An on-demand verify afterwards: in sync, wrong password refused.
    verify = await chr_lab.run((await chr_lab.request(account["id"], "verify"))["id"])
    assert verify["status"] == "succeeded" and verify["verify_result"] == "verified"
    state = await chr_lab.state(account["id"])
    assert state["sync_status"] == "in_sync" and state["secret_version"] == 2
    for step in done["steps"] + verify["steps"]:
        for text in (step["transcript"] or "", step["detail"] or ""):
            assert new not in text and original not in text
