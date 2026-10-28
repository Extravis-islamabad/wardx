"""Onboarding checks and rotation settings on accounts, targets and safes.

- WardX refuses an empty password; an existing empty one is flagged
  high_risk_empty_password (alert, account, dashboard).
- Reconcile accounts, target policy overrides and safe rotation policy are validated.
"""

from __future__ import annotations

import uuid

import pytest

from src.core.db import session_factory
from src.dependencies.rotation import build_rotation_scheduler_service
from src.dependencies.vault import build_vault_service
from src.services.inventory.account_service import ACCOUNT_SECRET
from tests.integration.rotation.rotation_support import sql

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_empty_or_blank_passwords_are_refused(rotlab, client, admin):
    target = await rotlab.target()
    for value in ("", "   "):
        resp = await client.post(
            "/accounts",
            headers=admin,
            json={"target_id": target["id"], "username": "wardx_rot_e", "secret": value},
        )
        assert resp.status_code in (409, 422), resp.text
    account = await rotlab.account(target=target)
    resp = await client.put(f"/accounts/{account['id']}/secret", headers=admin, json={"value": " "})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "empty_secret"


async def test_an_existing_empty_password_is_flagged_once(rotlab, client, admin):
    account = await rotlab.account()
    # A legacy empty secret written before the refusal existed (straight into the vault).
    async with session_factory()() as s:
        await build_vault_service(s).store(
            owner_type=ACCOUNT_SECRET,
            owner_id=uuid.UUID(account["id"]),
            version=2,
            plaintext="",
            created_by=None,
        )
        await s.commit()
    await sql("UPDATE inventory.accounts SET secret_version = 2 WHERE id = :a", a=account["id"])
    for _ in range(2):
        async with session_factory()() as s:
            await build_rotation_scheduler_service(s).scan_empty_passwords()
    state = await rotlab.state(account["id"])
    assert state["risk_flags"] == ["high_risk_empty_password"]
    assert (await rotlab.alerts(account["id"])).count("account.high_risk_empty_password") == 1
    shown = (await client.get(f"/accounts/{account['id']}", headers=admin)).json()["data"]
    assert shown["risk_flags"] == ["high_risk_empty_password"]
    att = (await client.get("/rotation/attention", headers=admin)).json()["data"]
    assert account["id"] in [a["id"] for a in att["empty_password"]]
    events = await sql(
        "SELECT safe_id FROM audit.events WHERE action = 'account.high_risk_empty_password' "
        "AND object_id = :a",
        a=account["id"],
    )
    assert len(events) == 1 and events[0]["safe_id"] is not None
    # Setting a real password clears the flag.
    resp = await client.put(
        f"/accounts/{account['id']}/secret", headers=admin, json={"value": "Real-Passw0rd-Now"}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["risk_flags"] == []


async def test_reconcile_account_rules(rotlab, client, admin):
    target = await rotlab.target()
    a = await rotlab.account(target=target)
    b = await rotlab.account(target=target)
    elsewhere = await rotlab.account()

    async def link(account, other):
        return await client.patch(
            f"/accounts/{account['id']}", headers=admin, json={"reconcile_account_id": other}
        )

    assert (await link(a, a["id"])).status_code == 409
    assert (await link(a, elsewhere["id"])).status_code == 409
    assert (await link(a, b["id"])).status_code == 200
    assert (await link(b, a["id"])).status_code == 409  # no mutual reconciling


async def test_target_policy_overrides_are_validated(client, admin):
    base = {"address": "192.0.2.20", "platform": "cisco_ios", "protocol": "ssh"}
    ok = await client.post(
        "/targets",
        headers=admin,
        json={
            **base,
            "name": f"ios-{uuid.uuid4().hex[:6]}",
            "policy_overrides": {"max_length": 16},
        },
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["data"]["policy_overrides"] == {"max_length": 16}
    assert ok.json()["data"]["rotation_allowed"] is False  # off by default
    bad = await client.post(
        "/targets",
        headers=admin,
        json={**base, "name": f"ios-{uuid.uuid4().hex[:6]}", "policy_overrides": {"symbols": "?"}},
    )
    assert bad.status_code == 422
    resp = await client.patch(
        f"/targets/{ok.json()['data']['id']}",
        headers=admin,
        json={"policy_overrides": {"min_length": 20, "max_length": 14}},
    )
    assert resp.status_code == 422


async def test_safe_rotation_policy_round_trip_and_validation(rotlab, client, admin):
    safe_id = await rotlab.safe()
    url = f"/safes/{safe_id}/rotation-policy"
    got = (await client.get(url, headers=admin)).json()["data"]
    assert got["rotate_after_use"] is False and got["max_release_wait_minutes"] == 240
    resp = await client.put(
        url,
        headers=admin,
        json={
            "rotate_after_use": True,
            "rotation_interval_days": 30,
            "maintenance_window": {"days": [5, 6], "start_hour": 1, "end_hour": 5},
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["maintenance_window"] == {
        "days": [5, 6],
        "start_hour": 1,
        "end_hour": 5,
    }
    bad = await client.put(
        url, headers=admin, json={"maintenance_window": {"days": [9], "start_hour": 0}}
    )
    assert bad.status_code == 422
    bad = await client.put(
        url,
        headers=admin,
        json={"maintenance_window": {"days": [1], "start_hour": 6, "end_hour": 2}},
    )
    assert bad.status_code == 422
