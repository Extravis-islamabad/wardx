"""Read scopes: command rules (commands.view), the audited break-glass account lookup,
and the safe-scoped audit (view_audit)."""

from __future__ import annotations

import pytest

from tests.integration.safes_support import ALL_PERMS, grant, me, new_account, new_safe, tag
from tests.integration.test_break_glass import make_holder

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.mark.parametrize(
    ("role", "allowed"), [("user", False), ("approver", False), ("auditor", True), ("admin", True)]
)
async def test_command_rules_and_tester_need_commands_view(client, make_user, role, allowed):
    headers = await make_user(f"cmd{role}{tag()}", role=role)
    listed = await client.get("/command-rules", headers=headers)
    tested = await client.post("/command-rules/test", headers=headers, json={"command": "reload"})
    expected = 200 if allowed else 403
    assert (listed.status_code, tested.status_code) == (expected, expected), tested.text
    assert ("commands.view" in (await me(client, headers))["permissions"]) is allowed


async def test_emergency_account_lookup_is_audited(client, admin, make_user):
    holder = await make_holder(client, admin, make_user)
    params = {"search": "core", "reason": "P1: core router outage INC-77"}
    resp = await client.get("/emergency/accounts", headers=holder["headers"], params=params)
    assert resp.status_code == 200
    events = (
        await client.get(
            "/audit/events",
            headers=admin,
            params={"action": "account.emergency_list", "actor_id": holder["user"]["id"]},
        )
    ).json()["data"]
    assert len(events) == 1
    details = events[0]["details"]
    assert (details["search"], details["reason"]) == ("core", params["reason"])
    alerts = (await client.get("/alerts", headers=admin, params={"page_size": 100})).json()["data"]
    assert not [a for a in alerts if a["actor_id"] == holder["user"]["id"] and "list" in a["kind"]]


async def test_safe_audit_needs_view_audit(client, admin, make_user):
    safe_id = await new_safe(client, admin)
    keeper = await make_user(f"keeper{tag()}", role="admin")
    await grant(client, admin, safe_id, "user", (await me(client, keeper))["id"], ALL_PERMS)
    account = await new_account(client, keeper, safe_id)
    lister = await make_user(f"al{tag()}")
    auditor_member = await make_user(f"av{tag()}")
    outsider = await make_user(f"ao{tag()}")
    await grant(client, admin, safe_id, "user", (await me(client, lister))["id"], ["list"])
    await grant(
        client,
        admin,
        safe_id,
        "user",
        (await me(client, auditor_member))["id"],
        ["list", "view_audit"],
    )
    url = f"/safes/{safe_id}/audit"
    assert (await client.get(url, headers=lister)).status_code == 403
    assert (await client.get(url, headers=outsider)).status_code == 404

    resp = await client.get(url, headers=auditor_member)
    assert resp.status_code == 200
    events = resp.json()["data"]
    actions = {(e["action"], e["object_id"]) for e in events}
    assert ("account.create", account["id"]) in actions
    assert ("safe.create", safe_id) in actions
    # Events of other safes are not included.
    assert all(e["object_id"] in {safe_id, account["id"]} for e in events)

    global_auditor = await make_user(f"ga{tag()}", role="auditor")
    assert (await client.get(url, headers=global_auditor)).status_code == 200
