"""End to end against the Linux lab container (ROTATION.md §9):

two-level approval → check-out → check-in → rotate-after-use waiting for an emergency
holder → rotation → verify. Plus the reconcile driver with a ':' in the password.
"""

from __future__ import annotations

import pytest

from src.rotation.drivers.base import (
    AccountRef,
    Credential,
    DriverContext,
    Outcome,
    TargetRef,
    Transcript,
)
from src.rotation.drivers.linux import LinuxDriver
from tests.integration.approvals_support import (
    APPROVER_PERMS,
    REQUESTER_PERMS,
    decide,
    person,
    request_access,
)
from tests.integration.rotation.linux_lab import requires_docker, start_container
from tests.integration.rotation.rotation_support import one
from tests.integration.rotation.test_linux_lab import LinuxLab
from tests.integration.test_break_glass import REASON, make_holder

pytestmark = [pytest.mark.asyncio(loop_scope="session"), requires_docker]


@pytest.fixture(scope="module")
async def box():
    container = await start_container(
        ["wardx_rot_e2e", "wardx_rot_colon", "wardx_rot_root"], sudo=("wardx_rot_root",)
    )
    yield container
    container.remove()


@pytest.fixture
async def linux(client, admin, box):
    from src.core.config import get_settings

    settings = get_settings()
    settings.rotation_enabled = True
    yield LinuxLab(client, admin, box)
    settings.rotation_enabled = False


async def test_approval_checkout_checkin_rotate_after_use_verify(
    linux, box, client, admin, make_user
):
    safe_id = await linux.safe(rotate_after_use=True)
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
    account = await linux.linux_account("wardx_rot_e2e", safe_id=safe_id)
    original = box.users["wardx_rot_e2e"]

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
    assert await box.login_works("wardx_rot_e2e", original)

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
    rotation = (await client.get(f"/accounts/{account['id']}/rotation", headers=admin)).json()[
        "data"
    ]
    job = rotation["open_job"]
    assert job["status"] == "waiting_release" and job["reason"] == "after_use"
    await linux.tick()
    assert (await linux.job(job["id"]))["status"] == "waiting_release"
    assert await box.login_works("wardx_rot_e2e", original)  # never rotated under a holder

    # The emergency holder checks in: the rotation runs and verifies.
    await client.post(
        f"/checkouts/{bg.json()['data']['checkout_id']}/checkin", headers=holder["headers"]
    )
    done = await linux.run(job["id"])
    assert done["status"] == "succeeded", done
    assert done["verify_result"] == "verified"
    new = await linux.current(account["id"])
    assert new != original
    assert await box.login_works("wardx_rot_e2e", new)
    assert not await box.login_works("wardx_rot_e2e", original)

    # An on-demand verify afterwards: in sync, wrong password refused.
    verify = await linux.run((await linux.request(account["id"], "verify"))["id"])
    assert verify["status"] == "succeeded" and verify["verify_result"] == "verified"
    state = await linux.state(account["id"])
    assert state["sync_status"] == "in_sync" and state["secret_version"] == 2


async def test_reconcile_driver_handles_a_colon_in_the_password(linux, box):
    target = await linux.linux_target()
    pinned = await one("SELECT ssh_host_key FROM inventory.targets WHERE id = :i", i=target["id"])
    ref = TargetRef(
        target["id"], target["name"], "127.0.0.1", box.port, "linux", "ssh", pinned["ssh_host_key"]
    )
    driver = LinuxDriver()
    ctx = DriverContext(Transcript([]), connect_timeout=10, command_timeout=10)
    session = await driver.connect(
        ref, Credential("wardx_rot_root", box.users["wardx_rot_root"]), ctx
    )
    new = "Colon:In-The:Middle-123"  # gitleaks:allow
    try:
        result = await driver.reconcile(session, AccountRef(1, "wardx_rot_colon"), new, ctx)
    finally:
        await session.close()
    assert result.outcome == Outcome.OK, result
    assert await box.login_works("wardx_rot_colon", new)
    assert new not in result.transcript
