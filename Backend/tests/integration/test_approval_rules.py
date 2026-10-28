"""Ticket modes and patterns, the approval window, single vs multi use, level timeout,
group-based approvers, and notifications for each step."""

from __future__ import annotations

import pytest

from tests.integration.approvals_support import (
    APPROVER_PERMS,
    REQUESTER_PERMS,
    approval_safe,
    decide,
    kinds_for,
    notifications,
    person,
    request_access,
    run_sql,
    set_policy,
    sweep,
)
from tests.integration.safes_support import grant, tag

pytestmark = pytest.mark.asyncio(loop_scope="session")

ONE_LEVEL = [{"required_approvals": 1}]


async def _setup(client, admin, make_user, **policy):
    lab = await approval_safe(client, admin, make_user, levels=ONE_LEVEL, **policy)
    lab["requester"] = await person(client, make_user, admin, lab["safe_id"], REQUESTER_PERMS)
    lab["approver"] = await person(client, make_user, admin, lab["safe_id"], APPROVER_PERMS)
    return lab


async def _approved(client, lab) -> dict:
    req = (await request_access(client, lab["requester"]["headers"], lab["account"]["id"])).json()[
        "data"
    ]
    done = (await decide(client, lab["approver"]["headers"], req["id"])).json()["data"]
    assert done["status"] == "approved"
    return done


async def _use(client, lab, request_id: str):
    return await client.post(
        "/checkouts",
        headers=lab["requester"]["headers"],
        json={"account_id": lab["account"]["id"], "request_id": request_id},
    )


async def test_ticket_required_with_pattern(client, admin, make_user):
    lab = await _setup(
        client, admin, make_user, ticket_mode="required", ticket_pattern=r"CHG-\d{4,8}"
    )
    who, aid = lab["requester"]["headers"], lab["account"]["id"]
    missing = await request_access(client, who, aid)
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "invalid_ticket"
    bad = await request_access(client, who, aid, ticket="INC-1234")
    assert bad.status_code == 422 and "does not match" in bad.text
    good = await request_access(client, who, aid, ticket="CHG-12345")
    assert good.status_code == 201 and good.json()["data"]["ticket_ref"] == "CHG-12345"


async def test_ticket_optional_and_off(client, admin, make_user):
    lab = await _setup(client, admin, make_user, ticket_mode="optional", ticket_pattern=r"T-\d+")
    who, aid = lab["requester"]["headers"], lab["account"]["id"]
    assert (await request_access(client, who, aid, ticket="nope")).status_code == 422
    first = await request_access(client, who, aid)
    assert first.status_code == 201 and first.json()["data"]["ticket_ref"] is None
    await client.post(f"/requests/{first.json()['data']['id']}/cancel", headers=who)
    assert (await request_access(client, who, aid, ticket="T-42")).status_code == 201

    off = await _setup(client, admin, make_user, ticket_mode="off", ticket_pattern=r"T-\d+")
    resp = await request_access(client, off["requester"]["headers"], off["account"]["id"], "x")
    assert resp.status_code == 201  # off: never validated


@pytest.mark.parametrize(
    ("pattern", "fragment"),
    [("(a+)+$", "nested quantifiers"), (r"(\w)\1", "backreferences"), ("CHG-(", "not a valid")],
)
async def test_unsafe_or_broken_patterns_are_refused(client, admin, make_user, pattern, fragment):
    lab = await approval_safe(client, admin, make_user)
    resp = await set_policy(
        client,
        admin,
        lab["safe_id"],
        levels=ONE_LEVEL,
        ticket_mode="required",
        ticket_pattern=pattern,
    )
    assert resp.status_code == 422 and fragment in resp.text
    too_long = await set_policy(
        client, admin, lab["safe_id"], levels=ONE_LEVEL, ticket_pattern="a" * 201
    )
    assert too_long.status_code == 422


async def test_single_use_is_spent_after_one_check_out(client, admin, make_user):
    lab = await _setup(client, admin, make_user)
    req = await _approved(client, lab)
    co = await _use(client, lab, req["id"])
    assert co.status_code == 201
    await client.post(
        f"/checkouts/{co.json()['data']['id']}/checkin", headers=lab["requester"]["headers"]
    )
    again = await _use(client, lab, req["id"])
    assert again.status_code == 409 and "used" in again.text


async def test_multi_use_counts_uses_within_the_window(client, admin, make_user):
    lab = await _setup(client, admin, make_user, approval_multi_use=True)
    req = await _approved(client, lab)
    for n in (1, 2):
        co = await _use(client, lab, req["id"])
        assert co.status_code == 201, co.text
        await client.post(
            f"/checkouts/{co.json()['data']['id']}/checkin", headers=lab["requester"]["headers"]
        )
        mine = (
            await client.get(
                "/requests", headers=lab["requester"]["headers"], params={"mine": True}
            )
        ).json()["data"]
        current = next(r for r in mine if r["id"] == req["id"])
        assert (current["status"], current["uses"]) == ("approved", n)


async def test_window_expiry_and_level_timeout_notify_the_requester(client, admin, make_user):
    lab = await _setup(client, admin, make_user, approval_window_minutes=30)
    req = await _approved(client, lab)
    # valid_until = approved_at + window.
    assert req["valid_until"] > req["approved_at"]
    await run_sql(
        "UPDATE access.requests SET expires_at = NOW() - INTERVAL '1 minute' WHERE id = :r",
        r=req["id"],
    )
    late = await _use(client, lab, req["id"])
    assert late.status_code == 409 and "expired" in late.text
    assert "request.expired" in await kinds_for(client, lab["requester"]["headers"], req["id"])

    # A level left undecided past level_timeout_hours expires (the sweeper).
    pending = (
        await request_access(client, lab["requester"]["headers"], lab["account"]["id"])
    ).json()["data"]
    await run_sql(
        "UPDATE access.requests SET expires_at = NOW() - INTERVAL '1 minute' WHERE id = :r",
        r=pending["id"],
    )
    assert (await sweep())["requests"] >= 1
    assert "request.expired" in await kinds_for(client, lab["requester"]["headers"], pending["id"])
    resp = await decide(client, lab["approver"]["headers"], pending["id"])
    assert resp.status_code == 409


async def test_notifications_for_each_step_and_recipient(client, admin, make_user):
    lab = await approval_safe(client, admin, make_user)
    sid = lab["safe_id"]
    requester = await person(client, make_user, admin, sid, REQUESTER_PERMS)
    a1 = await person(client, make_user, admin, sid, APPROVER_PERMS)
    a2 = await person(client, make_user, admin, sid, APPROVER_PERMS)
    await set_policy(
        client,
        admin,
        sid,
        levels=[
            {"approver_type": "user", "approver_key": a1["user"]["id"]},
            {"approver_type": "user", "approver_key": a2["user"]["id"]},
        ],
    )
    req = (await request_access(client, requester["headers"], lab["account"]["id"])).json()["data"]
    rid = req["id"]
    # Created: only the level-1 approver.
    assert await kinds_for(client, a1["headers"], rid) == ["request.pending"]
    assert await kinds_for(client, a2["headers"], rid) == []
    assert await kinds_for(client, requester["headers"], rid) == []

    # Advanced: the next approver and the requester.
    await decide(client, a1["headers"], rid)
    assert await kinds_for(client, a2["headers"], rid) == ["request.pending"]
    assert await kinds_for(client, requester["headers"], rid) == ["request.advanced"]

    # Approved: the requester.
    await decide(client, a2["headers"], rid)
    assert await kinds_for(client, requester["headers"], rid) == [
        "request.advanced",
        "request.approved",
    ]
    titles = sorted(
        n["title"]
        for n in await notifications(client, requester["headers"])
        if n["object_id"] == rid
    )
    assert titles[0].startswith("Level 1 of 2 approved") and titles[1].startswith(
        "Level 2 of 2 approved"
    )

    # Denied: the requester.
    await run_sql("UPDATE access.requests SET status = 'cancelled' WHERE id = :r", r=rid)
    second = (await request_access(client, requester["headers"], lab["account"]["id"])).json()
    await decide(client, a1["headers"], second["data"]["id"], approve=False)
    assert await kinds_for(client, requester["headers"], second["data"]["id"]) == ["request.denied"]

    # Unread count, mark one read, mark all read; nobody marks someone else's.
    count = (await client.get("/notifications/unread-count", headers=requester["headers"])).json()
    assert count["data"]["unread"] >= 3
    mine = (await client.get("/notifications", headers=requester["headers"])).json()["data"]
    other = await client.post(f"/notifications/{mine[0]['id']}/read", headers=a1["headers"])
    assert other.status_code == 404
    one = await client.post(f"/notifications/{mine[0]['id']}/read", headers=requester["headers"])
    assert one.status_code == 200
    after = (await client.get("/notifications/unread-count", headers=requester["headers"])).json()
    assert after["data"]["unread"] == count["data"]["unread"] - 1
    await client.post("/notifications/read-all", headers=requester["headers"])
    unread = await client.get(
        "/notifications", headers=requester["headers"], params={"unread_only": True}
    )
    assert unread.json()["total"] == 0


async def test_group_approvers_come_from_the_group_cache(client, admin, make_user):
    group = f"cn=Approvers-{tag()},ou=groups,dc=corp,dc=test"
    lab = await approval_safe(client, admin, make_user)
    sid = lab["safe_id"]
    await grant(client, admin, sid, "group", group, ["list", "approve"])
    requester = await person(client, make_user, admin, sid, REQUESTER_PERMS)
    in_group = await person(client, make_user, admin, sid, ["list"])
    not_in_group = await person(client, make_user, admin, sid, APPROVER_PERMS)
    resp = await set_policy(
        client, admin, sid, levels=[{"approver_type": "group", "approver_key": group}]
    )
    assert resp.status_code == 200, resp.text

    # Make in_group a directory user whose (fresh) cached groups include the group.
    uid = in_group["user"]["id"]
    await run_sql("UPDATE iam.users SET auth_source = 'ldap' WHERE id = :u", u=uid)
    await run_sql(
        "INSERT INTO iam.user_group_cache (user_id, groups, fetched_at) "
        "VALUES (:u, ARRAY[:g], NOW())",
        u=uid,
        g=group.lower(),
    )
    try:
        req = (await request_access(client, requester["headers"], lab["account"]["id"])).json()
        rid = req["data"]["id"]
        assert await kinds_for(client, in_group["headers"], rid) == ["request.pending"]
        assert await kinds_for(client, not_in_group["headers"], rid) == []
        refused = await decide(client, not_in_group["headers"], rid)
        assert refused.status_code == 403 and "directory group" in refused.text
        done = await decide(client, in_group["headers"], rid)
        assert done.status_code == 200 and done.json()["data"]["status"] == "approved"
    finally:
        # Directory sync tests expect only their own directory users.
        await run_sql("UPDATE iam.users SET auth_source = 'local' WHERE id = :u", u=uid)


async def test_partial_approval_at_a_level_notifies_nobody(client, admin, make_user):
    lab = await approval_safe(client, admin, make_user, levels=[{"required_approvals": 2}])
    sid = lab["safe_id"]
    requester = await person(client, make_user, admin, sid, REQUESTER_PERMS)
    a1 = await person(client, make_user, admin, sid, APPROVER_PERMS)
    a2 = await person(client, make_user, admin, sid, APPROVER_PERMS)
    req = (await request_access(client, requester["headers"], lab["account"]["id"])).json()
    rid = req["data"]["id"]
    await decide(client, a1["headers"], rid)
    assert await kinds_for(client, requester["headers"], rid) == []
    await decide(client, a2["headers"], rid)
    done = [
        n["title"]
        for n in await notifications(client, requester["headers"])
        if n["object_id"] == rid
    ]
    assert len(done) == 1 and done[0].startswith("Level 1 of 1 approved")
