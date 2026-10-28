"""Gateway sessions consume approved requests like check-outs: single use or multi use."""

from __future__ import annotations

import pytest

from tests.conftest import DEVICE_PASSWORD, DEVICE_USER
from tests.integration.approvals_support import APPROVER_PERMS, decide, person, request_access
from tests.integration.safes_support import ALL_PERMS, grant, me, new_safe, tag
from tests.integration.test_safes_gateway import _connect

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _lab(client, admin, make_user, device, multi_use: bool) -> dict:
    safe_id = await new_safe(client, admin)
    keeper = await person(client, make_user, admin, safe_id, ALL_PERMS, role="admin")
    target = (
        await client.post(
            "/targets",
            headers=keeper["headers"],
            json={
                "name": f"appr-rtr-{tag()}",
                "address": "127.0.0.1",
                "port": device.port,
                "platform": "cisco_ios",
                "protocol": "ssh",
            },
        )
    ).json()["data"]
    account = (
        await client.post(
            "/accounts",
            headers=keeper["headers"],
            json={
                "target_id": target["id"],
                "safe_id": safe_id,
                "username": DEVICE_USER,
                "secret": DEVICE_PASSWORD,
            },
        )
    ).json()["data"]
    resp = await client.put(
        f"/safes/{safe_id}/policy",
        headers=admin,
        json={
            "approval_required": True,
            "levels": [{"required_approvals": 1}],
            "approval_multi_use": multi_use,
        },
    )
    assert resp.status_code == 200, resp.text
    name = f"gwreq{tag()}"
    requester_headers = await make_user(name)
    await grant(
        client, admin, safe_id, "user", (await me(client, requester_headers))["id"], ["list", "use"]
    )
    approver = await person(client, make_user, admin, safe_id, APPROVER_PERMS)
    req = (await request_access(client, requester_headers, account["id"])).json()["data"]
    assert (await decide(client, approver["headers"], req["id"])).status_code == 200
    return {"name": name, "target": target, "request": req, "headers": requester_headers}


async def _session(gateway, lab) -> tuple[int, str, str]:
    conn = await _connect(
        gateway,
        f"{lab['name']}%{DEVICE_USER}%{lab['target']['name']}",
        f"User-Passw0rd-{lab['name']}",
    )
    result = await conn.run("show version", timeout=5)
    conn.close()
    return result.exit_status, result.stdout, result.stderr


async def _request(client, lab) -> dict:
    rows = (await client.get("/requests", headers=lab["headers"], params={"mine": True})).json()
    return next(r for r in rows["data"] if r["id"] == lab["request"]["id"])


async def test_single_use_approval_allows_one_gateway_session(
    gateway, device, client, admin, make_user
):
    lab = await _lab(client, admin, make_user, device, multi_use=False)
    status, out, _ = await _session(gateway, lab)
    assert status == 0 and "FakeOS 1.0" in out
    assert (await _request(client, lab))["status"] == "used"
    status, _, err = await _session(gateway, lab)
    assert status == 1 and "needs an approved request" in err


async def test_multi_use_approval_allows_several_sessions(
    gateway, device, client, admin, make_user
):
    lab = await _lab(client, admin, make_user, device, multi_use=True)
    for n in (1, 2):
        status, out, _ = await _session(gateway, lab)
        assert status == 0 and "FakeOS 1.0" in out
        current = await _request(client, lab)
        assert (current["status"], current["uses"]) == ("approved", n)
