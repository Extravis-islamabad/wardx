"""Safes: membership by user and role, 404 for unlisted accounts, separation of duties,
no self-grant, moving accounts, and the migrated Default safe."""

from __future__ import annotations

import pytest

from src.core.enums import DEFAULT_SAFE_ID
from tests.integration.safes_support import (
    ALL_PERMS,
    SECRET,
    add_member,
    checkout,
    grant,
    me,
    new_account,
    new_safe,
    tag,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture(scope="module")
async def keeper(client, admin, make_user):
    """A second admin who holds every permission on a fresh safe and owns one account in it.

    The bootstrap admin is deliberately not a member: safes.manage alone must not open it.
    """
    headers = await make_user(f"keeper{tag()}", role="admin")
    user = await me(client, headers)
    safe_id = await new_safe(client, admin)
    await grant(client, admin, safe_id, "user", user["id"], ALL_PERMS)
    account = await new_account(client, headers, safe_id)
    return {"headers": headers, "user": user, "safe_id": safe_id, "account": account}


async def test_default_safe_keeps_todays_access_through_role_members(client, admin):
    resp = await client.get(f"/safes/{DEFAULT_SAFE_ID}/members", headers=admin)
    assert resp.status_code == 200, resp.text
    roles = {m["principal_key"]: set(m["permissions"]) for m in resp.json()["data"]}
    base = {"list", "use", "retrieve"}
    assert roles["user"] == base and roles["auditor"] == base
    assert roles["approver"] == base | {"approve"}
    assert roles["admin"] == set(ALL_PERMS)


async def test_admin_without_membership_cannot_list_or_reveal(client, admin, keeper):
    account_id = keeper["account"]["id"]
    # safes.manage shows the safe itself, but no permissions on it.
    safe = (await client.get(f"/safes/{keeper['safe_id']}", headers=admin)).json()["data"]
    assert safe["my_permissions"] == [] and safe["account_count"] == 1

    listed = await client.get("/accounts", headers=admin, params={"safe_id": keeper["safe_id"]})
    assert listed.json()["data"] == []
    assert (await client.get(f"/accounts/{account_id}", headers=admin)).status_code == 404
    assert (await checkout(client, admin, account_id)).status_code == 404
    for method, path, body in (
        ("PATCH", f"/accounts/{account_id}", {"description": "x"}),
        ("PUT", f"/accounts/{account_id}/secret", {"value": "other"}),
        ("DELETE", f"/accounts/{account_id}", None),
    ):
        resp = await client.request(method, path, headers=admin, json=body)
        assert resp.status_code == 404, (method, resp.text)

    # The member sees and uses it.
    got = await client.get(f"/accounts/{account_id}", headers=keeper["headers"])
    assert got.status_code == 200 and got.json()["data"]["safe"]["id"] == keeper["safe_id"]


async def test_user_membership_grants_exactly_its_permissions(client, admin, keeper, make_user):
    name = f"member{tag()}"
    headers = await make_user(name)
    user = await me(client, headers)
    account_id = keeper["account"]["id"]
    assert (await client.get(f"/accounts/{account_id}", headers=headers)).status_code == 404

    member = await grant(client, admin, keeper["safe_id"], "user", user["id"], ["list"])
    assert member["display_name"] == name
    assert (await client.get(f"/accounts/{account_id}", headers=headers)).status_code == 200
    refused = await checkout(client, headers, account_id)
    assert refused.status_code == 403 and "retrieve" in refused.json()["error"]["message"]

    await client.patch(
        f"/safes/{keeper['safe_id']}/members/{member['id']}",
        headers=admin,
        json={"permissions": ["list", "retrieve"]},
    )
    co = await checkout(client, headers, account_id)
    assert co.status_code == 201, co.text
    reveal = await client.post(f"/checkouts/{co.json()['data']['id']}/reveal", headers=headers)
    assert reveal.status_code == 200 and reveal.json()["data"]["value"] == SECRET

    # Losing retrieve mid check-out stops the next reveal.
    await client.patch(
        f"/safes/{keeper['safe_id']}/members/{member['id']}",
        headers=admin,
        json={"permissions": ["list", "use"]},
    )
    again = await client.post(f"/checkouts/{co.json()['data']['id']}/reveal", headers=headers)
    assert again.status_code == 403
    await client.post(f"/checkouts/{co.json()['data']['id']}/checkin", headers=headers)

    # A plain user cannot manage accounts even as a member (inventory.manage gates the route).
    edit = await client.patch(f"/accounts/{account_id}", headers=headers, json={"description": "x"})
    assert edit.status_code == 403


async def test_role_membership_applies_to_everyone_in_the_role(client, admin, make_user):
    safe_id = await new_safe(client, admin)
    keeper2 = await make_user(f"keeper{tag()}", role="admin")
    await grant(client, admin, safe_id, "user", (await me(client, keeper2))["id"], ALL_PERMS)
    account = await new_account(client, keeper2, safe_id)
    auditor = await make_user(f"aud{tag()}", role="auditor")
    assert (await client.get(f"/accounts/{account['id']}", headers=auditor)).status_code == 404

    await grant(client, admin, safe_id, "role", "auditor", ["list", "retrieve"])
    assert (await client.get(f"/accounts/{account['id']}", headers=auditor)).status_code == 200
    assert (await checkout(client, auditor, account["id"])).status_code == 201


async def test_safe_list_shows_only_listable_safes_to_non_admins(client, admin, keeper, make_user):
    headers = await make_user(f"viewer{tag()}")
    ids = {s["id"] for s in (await client.get("/safes", headers=headers)).json()["data"]}
    assert str(DEFAULT_SAFE_ID) in ids and keeper["safe_id"] not in ids
    assert (await client.get(f"/safes/{keeper['safe_id']}", headers=headers)).status_code == 404
    members = await client.get(f"/safes/{keeper['safe_id']}/members", headers=headers)
    assert members.status_code == 404
    # Listing the Default safe is not managing it.
    members = await client.get(f"/safes/{DEFAULT_SAFE_ID}/members", headers=headers)
    assert members.status_code == 403
    assert (await client.post("/safes", headers=headers, json={"name": "nope"})).status_code == 403


async def test_no_self_grant_for_user_or_own_role(client, admin, keeper):
    me_admin = await me(client, admin)
    resp = await add_member(client, admin, keeper["safe_id"], "user", me_admin["id"], ["list"])
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "self_grant_forbidden"
    resp = await add_member(client, admin, keeper["safe_id"], "role", "admin", ["list"])
    assert resp.json()["error"]["code"] == "self_grant_forbidden"

    # Widening (or changing at all) your own existing membership is refused too.
    members = (
        await client.get(f"/safes/{keeper['safe_id']}/members", headers=keeper["headers"])
    ).json()["data"]
    own = next(m for m in members if m["principal_key"] == keeper["user"]["id"])
    resp = await client.patch(
        f"/safes/{keeper['safe_id']}/members/{own['id']}",
        headers=keeper["headers"],
        json={"permissions": ["list"]},
    )
    assert resp.json()["error"]["code"] == "self_grant_forbidden"

    events = (
        await client.get(
            "/audit/events",
            headers=admin,
            params={"action": "safe_member.add", "actor_id": me_admin["id"]},
        )
    ).json()["data"]
    failures = [e for e in events if e["outcome"] == "failure"]
    assert failures and failures[0]["details"]["reason"] == "self_grant_forbidden"


async def test_manage_members_holder_manages_only_that_safe(client, admin, keeper, make_user):
    lead = await make_user(f"lead{tag()}")
    lead_user = await me(client, lead)
    await grant(
        client, admin, keeper["safe_id"], "user", lead_user["id"], ["list", "manage_members"]
    )
    other = await me(client, await make_user(f"other{tag()}"))
    added = await add_member(client, lead, keeper["safe_id"], "user", other["id"], ["list"])
    assert added.status_code == 201, added.text
    assert (await add_member(client, lead, keeper["safe_id"], "role", "user", ["list"])).json()[
        "error"
    ]["code"] == "self_grant_forbidden"

    # Every change is audited with before and after.
    member_id = added.json()["data"]["id"]
    await client.patch(
        f"/safes/{keeper['safe_id']}/members/{member_id}",
        headers=lead,
        json={"permissions": ["list", "use"]},
    )
    event = (
        await client.get(
            "/audit/events",
            headers=admin,
            params={"action": "safe_member.update", "actor_id": lead_user["id"]},
        )
    ).json()["data"][0]
    assert event["details"]["before"]["permissions"] == ["list"]
    assert event["details"]["after"]["permissions"] == ["list", "use"]
    removed = await client.delete(f"/safes/{keeper['safe_id']}/members/{member_id}", headers=lead)
    assert removed.status_code == 200

    other_safe = await new_safe(client, admin)
    assert (await client.get(f"/safes/{other_safe}/members", headers=lead)).status_code == 404


async def test_moving_an_account_needs_manage_accounts_on_both_safes(client, admin, keeper):
    account = await new_account(client, keeper["headers"], keeper["safe_id"])
    dest = await new_safe(client, admin)
    move = {"safe_id": dest}
    url = f"/accounts/{account['id']}"
    assert (await client.patch(url, headers=keeper["headers"], json=move)).status_code == 404

    member = await grant(client, admin, dest, "user", keeper["user"]["id"], ["list"])
    assert (await client.patch(url, headers=keeper["headers"], json=move)).status_code == 403

    await client.patch(
        f"/safes/{dest}/members/{member['id']}",
        headers=admin,
        json={"permissions": ["list", "manage_accounts"]},
    )
    moved = await client.patch(url, headers=keeper["headers"], json=move)
    assert moved.status_code == 200 and moved.json()["data"]["safe"]["id"] == dest

    # Creating into a safe you cannot manage is refused as well.
    resp = await client.post(
        "/accounts",
        headers=admin,
        json={"target_id": account["target"]["id"], "safe_id": dest, "username": "other"},
    )
    assert resp.status_code == 404


async def test_inactive_safe_blocks_use_but_keeps_listing(client, admin, make_user):
    safe_id = await new_safe(client, admin)
    owner = await make_user(f"keeper{tag()}", role="admin")
    await grant(client, admin, safe_id, "user", (await me(client, owner))["id"], ALL_PERMS)
    account = await new_account(client, owner, safe_id)
    resp = await client.patch(f"/safes/{safe_id}", headers=admin, json={"is_active": False})
    assert resp.status_code == 200 and resp.json()["data"]["is_active"] is False
    assert (await client.get(f"/accounts/{account['id']}", headers=owner)).status_code == 200
    assert (await checkout(client, owner, account["id"])).status_code == 403


async def test_safe_names_are_unique_ignoring_case(client, admin):
    name = f"Unique-{tag()}"
    await new_safe(client, admin, name)
    dup = await client.post("/safes", headers=admin, json={"name": name.lower()})
    assert dup.status_code == 409
