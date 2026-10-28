"""The approval workflow: levels, dual control, who may decide, deny, the queue, and
the audit trail of decisions."""

from __future__ import annotations

import pytest

from tests.integration.approvals_support import (
    APPROVER_PERMS,
    REQUESTER_PERMS,
    approval_safe,
    decide,
    person,
    request_access,
    set_policy,
)
from tests.integration.safes_support import checkout, tag

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_dual_control_needs_two_different_approvers(client, admin, make_user):
    lab = await approval_safe(client, admin, make_user, levels=[{"required_approvals": 2}])
    sid, account_id = lab["safe_id"], lab["account"]["id"]
    requester = await person(client, make_user, admin, sid, REQUESTER_PERMS)
    a1 = await person(client, make_user, admin, sid, APPROVER_PERMS)
    a2 = await person(client, make_user, admin, sid, APPROVER_PERMS)

    # Without an approved request, no check-out.
    assert (await checkout(client, requester["headers"], account_id)).status_code == 403
    req = (await request_access(client, requester["headers"], account_id)).json()["data"]
    assert (req["status"], req["current_level"], req["level_count"]) == ("pending", 1, 1)

    first = (await decide(client, a1["headers"], req["id"])).json()["data"]
    assert first["status"] == "pending" and first["levels"][0]["approvals"] == 1
    again = await decide(client, a1["headers"], req["id"])
    assert again.status_code == 403 and "one decision per person" in again.text

    done = (await decide(client, a2["headers"], req["id"])).json()["data"]
    assert done["status"] == "approved" and done["valid_until"] is not None
    assert [d["approver"]["id"] for d in done["decisions"]] == [a1["user"]["id"], a2["user"]["id"]]

    co = await client.post(
        "/checkouts",
        headers=requester["headers"],
        json={"account_id": account_id, "request_id": req["id"]},
    )
    assert co.status_code == 201, co.text


async def test_two_level_chain_and_nobody_approves_twice(client, admin, make_user):
    lab = await approval_safe(client, admin, make_user)
    sid, account_id = lab["safe_id"], lab["account"]["id"]
    requester = await person(client, make_user, admin, sid, REQUESTER_PERMS)
    a1 = await person(client, make_user, admin, sid, APPROVER_PERMS)
    manager = await person(client, make_user, admin, sid, APPROVER_PERMS)
    bystander = await person(client, make_user, admin, sid, APPROVER_PERMS)
    resp = await set_policy(
        client,
        admin,
        sid,
        levels=[
            {"required_approvals": 1},
            {"approver_type": "user", "approver_key": manager["user"]["id"]},
        ],
    )
    assert resp.status_code == 200, resp.text

    req = (await request_access(client, requester["headers"], account_id)).json()["data"]
    # Level 1 is any safe approver: a1 decides it.
    after_l1 = (await decide(client, a1["headers"], req["id"])).json()["data"]
    assert (after_l1["status"], after_l1["current_level"]) == ("pending", 2)
    assert [lv["state"] for lv in after_l1["levels"]] == ["approved", "current"]

    # a1 decided level 1, so cannot decide level 2; the bystander is not the named user.
    resp = await decide(client, a1["headers"], req["id"])
    assert resp.status_code == 403 and "one decision per person" in resp.text
    resp = await decide(client, bystander["headers"], req["id"])
    assert resp.status_code == 403 and "named user" in resp.text

    final = (await decide(client, manager["headers"], req["id"])).json()["data"]
    assert final["status"] == "approved"
    assert [lv["state"] for lv in final["levels"]] == ["approved", "approved"]

    events = (
        await client.get(
            "/audit/events",
            headers=admin,
            params={"action": "request.approve", "object_id": req["id"]},
        )
    ).json()["data"]
    assert sorted(e["details"]["level"] for e in events) == [1, 2]


async def test_requester_never_approves_and_deny_ends_the_request(client, admin, make_user):
    lab = await approval_safe(client, admin, make_user, levels=[{"required_approvals": 1}])
    sid, account_id = lab["safe_id"], lab["account"]["id"]
    # The requester holds 'approve' too.
    requester = await person(client, make_user, admin, sid, REQUESTER_PERMS + ["approve"])
    approver = await person(client, make_user, admin, sid, APPROVER_PERMS)
    outsider = await make_user(f"out{tag()}")

    req = (await request_access(client, requester["headers"], account_id)).json()["data"]
    own = await decide(client, requester["headers"], req["id"])
    assert own.status_code == 403 and "your own request" in own.text
    # No 'approve' on the safe: refused.
    assert (await decide(client, outsider, req["id"])).status_code in (403, 404)

    denied = (await decide(client, approver["headers"], req["id"], approve=False)).json()["data"]
    assert denied["status"] == "denied" and denied["levels"][0]["state"] == "denied"
    late = await decide(client, approver["headers"], req["id"])
    assert late.status_code == 409


async def test_queue_shows_only_what_you_can_decide_now(client, admin, make_user):
    lab = await approval_safe(client, admin, make_user)
    sid, account_id = lab["safe_id"], lab["account"]["id"]
    requester = await person(client, make_user, admin, sid, REQUESTER_PERMS)
    a1 = await person(client, make_user, admin, sid, APPROVER_PERMS)
    manager = await person(client, make_user, admin, sid, APPROVER_PERMS)
    await set_policy(
        client,
        admin,
        sid,
        levels=[
            {"approver_type": "user", "approver_key": a1["user"]["id"]},
            {"approver_type": "user", "approver_key": manager["user"]["id"]},
        ],
    )
    req = (await request_access(client, requester["headers"], account_id)).json()["data"]

    async def queue(headers) -> set[str]:
        rows = (await client.get("/requests", headers=headers, params={"queue": True})).json()
        return {r["id"] for r in rows["data"]}

    assert req["id"] in await queue(a1["headers"])
    assert req["id"] not in await queue(manager["headers"])
    assert req["id"] not in await queue(requester["headers"])
    await decide(client, a1["headers"], req["id"])
    assert req["id"] not in await queue(a1["headers"])
    assert req["id"] in await queue(manager["headers"])


async def test_policy_validation(client, admin, make_user):
    lab = await approval_safe(client, admin, make_user)
    sid = lab["safe_id"]
    no_approve = await person(client, make_user, admin, sid, ["list"])

    resp = await set_policy(client, admin, sid, levels=[])
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "invalid_policy"
    resp = await set_policy(
        client,
        admin,
        sid,
        levels=[{"approver_type": "user", "approver_key": no_approve["user"]["id"]}],
    )
    assert resp.status_code == 422 and "hold 'approve'" in resp.text
    resp = await set_policy(
        client, admin, sid, levels=[{"approver_type": "group", "approver_key": "cn=x,dc=corp"}]
    )
    assert resp.status_code == 422 and "member of the safe" in resp.text
    # Only safes.manage saves a policy; members with list can read it.
    assert (
        await client.put(f"/safes/{sid}/policy", headers=no_approve["headers"], json={})
    ).status_code == 403
    got = await client.get(f"/safes/{sid}/policy", headers=no_approve["headers"])
    assert got.status_code == 200 and got.json()["data"]["approval_required"] is False

    # Before/after audited.
    ok = await set_policy(client, admin, sid, levels=[{"required_approvals": 2}])
    assert ok.status_code == 200
    events = (
        await client.get(
            "/audit/events",
            headers=admin,
            params={"action": "safe.policy_update", "object_id": sid},
        )
    ).json()["data"]
    assert events[0]["details"]["after"]["levels"][0]["required_approvals"] == 2


async def test_account_shows_its_safes_approval_need(client, admin, make_user):
    lab = await approval_safe(client, admin, make_user)
    url = f"/accounts/{lab['account']['id']}"
    keeper = lab["keeper"]["headers"]
    assert (await client.get(url, headers=keeper)).json()["data"]["requires_approval"] is False
    await set_policy(client, admin, lab["safe_id"], levels=[{"required_approvals": 1}])
    assert (await client.get(url, headers=keeper)).json()["data"]["requires_approval"] is True
    # Requests on a safe without approval are refused.
    plain = await approval_safe(client, admin, make_user)
    resp = await request_access(client, plain["keeper"]["headers"], plain["account"]["id"])
    assert resp.status_code == 409


async def test_queue_is_paged_in_the_database(client, admin, make_user):
    lab = await approval_safe(client, admin, make_user, levels=[{"required_approvals": 1}])
    sid, account_id = lab["safe_id"], lab["account"]["id"]
    approver = await person(client, make_user, admin, sid, APPROVER_PERMS)
    created = []
    for _ in range(3):
        requester = await person(client, make_user, admin, sid, REQUESTER_PERMS)
        resp = await request_access(client, requester["headers"], account_id)
        created.append(resp.json()["data"]["id"])

    async def page(n: int) -> dict:
        params = {"queue": True, "page": n, "page_size": 2}
        return (await client.get("/requests", headers=approver["headers"], params=params)).json()

    first, second = await page(1), await page(2)
    assert first["total"] == second["total"] == 3
    assert [r["id"] for r in first["data"]] + [r["id"] for r in second["data"]] == created
    # Deciding one removes it from the queue.
    await decide(client, approver["headers"], created[0])
    assert (await page(1))["total"] == 2
