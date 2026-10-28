"""Audit events keep the safe they happened in: moving an account doesn't move its past."""

from __future__ import annotations

import pytest

from tests.integration.safes_support import (
    ALL_PERMS,
    checkout,
    grant,
    me,
    new_account,
    new_safe,
    tag,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _events(client, admin, safe_id: str) -> list[dict]:
    resp = await client.get(f"/safes/{safe_id}/audit", headers=admin, params={"page_size": 200})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def test_events_stay_with_the_safe_they_happened_in(client, admin, make_user):
    safe_a, safe_b = await new_safe(client, admin), await new_safe(client, admin)
    keeper = await make_user(f"keeper{tag()}", role="admin")
    keeper_id = (await me(client, keeper))["id"]
    for sid in (safe_a, safe_b):
        await grant(client, admin, sid, "user", keeper_id, ALL_PERMS)
    account = await new_account(client, keeper, safe_a)
    co = (await checkout(client, keeper, account["id"])).json()["data"]
    await client.post(f"/checkouts/{co['id']}/reveal", headers=keeper)
    await client.post(f"/checkouts/{co['id']}/checkin", headers=keeper)

    moved = await client.patch(
        f"/accounts/{account['id']}", headers=keeper, json={"safe_id": safe_b}
    )
    assert moved.status_code == 200
    await client.put(f"/accounts/{account['id']}/secret", headers=keeper, json={"value": "new-1"})

    in_a = {e["action"] for e in await _events(client, admin, safe_a)}
    in_b = {e["action"] for e in await _events(client, admin, safe_b)}
    before_move = {"account.create", "checkout.create", "secret.reveal", "checkout.return"}
    assert before_move <= in_a
    assert "account.update" in in_a  # the move is recorded where the account left
    assert not before_move & in_b
    assert "secret.set" in in_b and "secret.set" not in in_a
    assert all(e["safe_id"] == safe_b for e in await _events(client, admin, safe_b) if e["safe_id"])


async def test_target_delete_is_recorded_in_every_affected_safe(client, admin, make_user):
    safe_a, safe_b = await new_safe(client, admin), await new_safe(client, admin)
    keeper = await make_user(f"keeper{tag()}", role="admin")
    keeper_id = (await me(client, keeper))["id"]
    for sid in (safe_a, safe_b):
        await grant(client, admin, sid, "user", keeper_id, ALL_PERMS)
    target = (
        await client.post(
            "/targets",
            headers=keeper,
            json={
                "name": f"t-{tag()}",
                "address": "10.0.0.7",
                "platform": "linux",
                "protocol": "ssh",
            },
        )
    ).json()["data"]
    made = {}
    for sid, username in ((safe_a, "alpha"), (safe_a, "beta"), (safe_b, "gamma")):
        resp = await client.post(
            "/accounts",
            headers=keeper,
            json={"target_id": target["id"], "safe_id": sid, "username": username},
        )
        made[username] = resp.json()["data"]["id"]
    assert (await client.delete(f"/targets/{target['id']}", headers=keeper)).status_code == 200

    def deletion(events):
        return [e for e in events if e["action"] == "target.delete"]

    in_a = deletion(await _events(client, admin, safe_a))
    in_b = deletion(await _events(client, admin, safe_b))
    assert len(in_a) == len(in_b) == 1
    assert sorted(a["username"] for a in in_a[0]["details"]["accounts_removed"]) == [
        "alpha",
        "beta",
    ]
    assert in_b[0]["details"]["accounts_removed"] == [{"id": made["gamma"], "username": "gamma"}]
    # The target-level event is kept, without a safe.
    everything = (
        await client.get(
            "/audit/events",
            headers=admin,
            params={"action": "target.delete", "object_id": target["id"]},
        )
    ).json()["data"]
    assert len(everything) == 3 and sum(e["safe_id"] is None for e in everything) == 1
