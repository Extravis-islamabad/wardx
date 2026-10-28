"""Break-glass (access.emergency): who may hold it, using it with the directory down,
the MFA safeguards, re-granting after an automatic revoke, and security alerts."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import ldap3
import pytest
from sqlalchemy import text

from src.core import totp
from src.core.db import session_factory
from src.services.directory import directory_service
from tests.integration.safes_support import ALL_PERMS, SECRET, grant, me, new_account, new_safe, tag
from tests.integration.test_directory import CONFIG
from tests.ldap_mock import build_directory, mock_factory

pytestmark = pytest.mark.asyncio(loop_scope="session")

REASON = "P1 outage: core router down, on-call needs the enable secret"
EMERGENCY = "access.emergency"


async def enrol(client, headers) -> tuple[str, dict]:
    """Turn MFA on; returns (seed, fresh headers)."""
    setup = (await client.post("/auth/mfa/setup", headers=headers)).json()["data"]
    seed = parse_qs(urlparse(setup["otpauth_uri"]).query)["secret"][0]
    resp = await client.post(
        "/auth/mfa/enable",
        headers=headers,
        json={"code": totp.code_at(seed, totp.current_step())},
    )
    assert resp.status_code == 200, resp.text
    return seed, {"Authorization": f"Bearer {resp.json()['data']['tokens']['access_token']}"}


async def sign_in_with_mfa(client, username: str, password: str, seed: str, step: int) -> dict:
    first = (
        await client.post("/auth/login", json={"username": username, "password": password})
    ).json()["data"]
    assert first["mfa_required"] is True
    resp = await client.post(
        "/auth/mfa/verify",
        json={"mfa_token": first["mfa_token"], "code": totp.code_at(seed, step)},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def make_holder(client, admin, make_user, role: str = "user") -> dict:
    """A local, MFA-enrolled user holding access.emergency (granted by the bootstrap admin)."""
    name = f"bg{tag()}"
    seed, headers = await enrol(client, await make_user(name, role=role))
    user = await me(client, headers)
    resp = await client.put(f"/users/{user['id']}/permissions/{EMERGENCY}", headers=admin)
    assert resp.status_code == 200, resp.text
    return {"name": name, "seed": seed, "headers": headers, "user": user}


async def _locked_account(client, admin, make_user) -> dict:
    """An account in a safe neither the bootstrap admin nor the holders belong to."""
    safe_id = await new_safe(client, admin)
    keeper = await make_user(f"keeper{tag()}", role="admin")
    await grant(client, admin, safe_id, "user", (await me(client, keeper))["id"], ALL_PERMS)
    return await new_account(client, keeper, safe_id)


async def _alerts(client, admin, kind: str, object_id: str) -> list[dict]:
    rows = (await client.get("/alerts", headers=admin, params={"page_size": 100})).json()["data"]
    return [a for a in rows if a["kind"] == kind and a["object_id"] == object_id]


async def _set_source(user_id: str, source: str) -> None:
    async with session_factory()() as s:
        await s.execute(
            text("UPDATE iam.users SET auth_source = :src WHERE id = :u"),
            {"u": user_id, "src": source},
        )
        await s.commit()


async def test_only_local_mfa_users_can_be_granted(client, admin, make_user):
    no_mfa = await me(client, await make_user(f"nomfa{tag()}"))
    resp = await client.put(f"/users/{no_mfa['id']}/permissions/{EMERGENCY}", headers=admin)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "not_eligible"
    assert "MFA" in resp.json()["error"]["message"]

    _, headers = await enrol(client, await make_user(f"dir{tag()}"))
    directory_user = await me(client, headers)
    await _set_source(directory_user["id"], "ldap")
    try:
        resp = await client.put(
            f"/users/{directory_user['id']}/permissions/{EMERGENCY}", headers=admin
        )
        assert resp.status_code == 409 and "directory" in resp.json()["error"]["message"]
    finally:
        # Directory sync tests expect only their own directory users.
        await _set_source(directory_user["id"], "local")

    admin_me = await me(client, admin)
    resp = await client.put(f"/users/{admin_me['id']}/permissions/{EMERGENCY}", headers=admin)
    assert resp.json()["error"]["code"] == "self_grant_forbidden"
    # Only access.emergency is grantable, and only by users.manage holders.
    assert (
        await client.put(f"/users/{no_mfa['id']}/permissions/users.manage", headers=admin)
    ).status_code == 422
    assert (
        await client.put(f"/users/{no_mfa['id']}/permissions/{EMERGENCY}", headers=headers)
    ).status_code == 403


async def test_grant_shows_in_me_and_users_and_raises_an_alert(client, admin, make_user):
    holder = await make_holder(client, admin, make_user)
    mine = await me(client, holder["headers"])
    assert EMERGENCY in mine["permissions"] and mine["direct_permissions"] == [EMERGENCY]
    assert EMERGENCY not in (await me(client, admin))["permissions"]
    listed = (await client.get("/users", headers=admin, params={"search": holder["name"]})).json()[
        "data"
    ][0]
    assert listed["direct_permissions"] == [EMERGENCY] and listed["mfa_enabled"] is True
    assert await _alerts(client, admin, "break_glass.granted", holder["user"]["id"])


async def test_emergency_reveal_works_with_the_directory_down(client, admin, make_user):
    holder = await make_holder(client, admin, make_user)
    account = await _locked_account(client, admin, make_user)
    # The holder is not a member: the account does not even exist for normal access.
    assert (
        await client.get(f"/accounts/{account['id']}", headers=holder["headers"])
    ).status_code == 404

    directory_service.set_connection_factory(mock_factory(build_directory()))
    assert (await client.put("/directory", headers=admin, json=CONFIG)).status_code == 200

    def broken(*_):
        raise ldap3.core.exceptions.LDAPSocketOpenError("connection refused")

    directory_service.set_connection_factory(broken)
    try:
        # A directory user can't sign in now; the local holder can (password + TOTP).
        down = await client.post(
            "/auth/login", json={"username": "akhan", "password": "Dir-Pass-akhan1"}
        )
        assert down.status_code == 502
        headers = await sign_in_with_mfa(
            client,
            holder["name"],
            f"User-Passw0rd-{holder['name']}",
            holder["seed"],
            totp.current_step() + 1,
        )
        resp = await client.post(
            f"/accounts/{account['id']}/emergency-reveal", headers=headers, json={"reason": REASON}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["value"] == SECRET
    finally:
        await client.put("/directory", headers=admin, json={**CONFIG, "enabled": False})
        directory_service.set_connection_factory(directory_service.default_connection)

    checkout_id = resp.json()["data"]["checkout_id"]
    mine = (await client.get("/checkouts", headers=headers, params={"mine": True})).json()["data"]
    record = next(c for c in mine if c["id"] == checkout_id)
    assert record["emergency"] is True and record["reason"] == REASON

    events = (
        await client.get(
            "/audit/events", headers=admin, params={"action": "secret.emergency_reveal"}
        )
    ).json()["data"]
    event = next(e for e in events if e["object_id"] == checkout_id)
    assert event["outcome"] == "success" and event["details"]["reason"] == REASON

    alert = (await _alerts(client, admin, "break_glass.used", account["id"]))[0]
    assert alert["severity"] == "high" and alert["acknowledged_at"] is None
    assert alert["details"]["reason"] == REASON


async def test_reveal_rules(client, admin, make_user):
    holder = await make_holder(client, admin, make_user)
    account = await _locked_account(client, admin, make_user)
    url = f"/accounts/{account['id']}/emergency-reveal"
    # Holders can find accounts in safes they are not members of (metadata only).
    params = {"search": account["target"]["name"]}
    found = await client.get("/emergency/accounts", headers=holder["headers"], params=params)
    assert [a["id"] for a in found.json()["data"]] == [account["id"]]
    assert "value" not in found.text
    plain_headers = await make_user(f"plainlist{tag()}")
    assert (await client.get("/emergency/accounts", headers=plain_headers)).status_code == 403
    short = await client.post(url, headers=holder["headers"], json={"reason": "too short"})
    assert short.status_code == 422
    plain = await make_user(f"plain{tag()}")
    assert (await client.post(url, headers=plain, json={"reason": REASON})).status_code == 403
    # Admins don't hold it by role.
    assert (await client.post(url, headers=admin, json={"reason": REASON})).status_code == 403

    # MFA is re-checked at the moment of use.
    async with session_factory()() as s:
        await s.execute(
            text("UPDATE iam.user_mfa SET enabled = FALSE WHERE user_id = :u"),
            {"u": holder["user"]["id"]},
        )
        await s.commit()
    resp = await client.post(url, headers=holder["headers"], json={"reason": REASON})
    assert resp.status_code == 403 and "MFA" in resp.json()["error"]["message"]


async def test_holder_cannot_turn_their_own_mfa_off(client, admin, make_user):
    holder = await make_holder(client, admin, make_user)
    resp = await client.post(
        "/auth/mfa/disable",
        headers=holder["headers"],
        json={"code": totp.code_at(holder["seed"], totp.current_step() + 1)},
    )
    assert resp.status_code == 409 and "break-glass" in resp.json()["error"]["message"]


async def test_mfa_reset_revokes_and_regrant_needs_another_admin(client, admin, make_user):
    holder = await make_holder(client, admin, make_user, role="admin")
    user_id = holder["user"]["id"]
    resp = await client.post(f"/users/{user_id}/mfa/reset", headers=admin)
    assert resp.status_code == 200, resp.text
    revoked = await _alerts(client, admin, "break_glass.revoked", user_id)
    assert revoked and revoked[0]["details"]["reason"] == "mfa_reset"
    events = (
        await client.get(
            "/audit/events", headers=admin, params={"action": "user.revoke", "object_id": user_id}
        )
    ).json()["data"]
    assert events and events[0]["details"]["reason"] == "mfa_reset"

    # The holder re-enrols but can't re-grant themselves, even as an admin.
    password = f"User-Passw0rd-{holder['name']}"
    login = await client.post(
        "/auth/login", json={"username": holder["name"], "password": password}
    )
    fresh = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    _, fresh = await enrol(client, fresh)
    assert EMERGENCY not in (await me(client, fresh))["permissions"]
    resp = await client.put(f"/users/{user_id}/permissions/{EMERGENCY}", headers=fresh)
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "self_grant_forbidden"
    resp = await client.put(f"/users/{user_id}/permissions/{EMERGENCY}", headers=admin)
    assert resp.status_code == 200, resp.text
    assert EMERGENCY in (await me(client, fresh))["permissions"]

    # A plain revoke is audited and alerted too.
    assert (
        await client.delete(f"/users/{user_id}/permissions/{EMERGENCY}", headers=admin)
    ).status_code == 200
    assert len(await _alerts(client, admin, "break_glass.revoked", user_id)) == 2


async def test_alerts_are_listed_acknowledged_once_and_never_deleted(client, admin, make_user):
    holder = await make_holder(client, admin, make_user)
    alert = (await _alerts(client, admin, "break_glass.granted", holder["user"]["id"]))[0]
    auditor = await make_user(f"aud{tag()}", role="auditor")
    listed = await client.get(
        "/alerts", headers=auditor, params={"severity": "high", "acknowledged": False}
    )
    assert listed.status_code == 200 and any(a["id"] == alert["id"] for a in listed.json()["data"])
    url = f"/alerts/{alert['id']}/acknowledge"
    assert (await client.post(url, headers=auditor)).status_code == 403
    done = await client.post(url, headers=admin)
    assert done.status_code == 200 and done.json()["data"]["acknowledged_at"] is not None
    assert (await client.post(url, headers=admin)).status_code == 409
    events = (
        await client.get(
            "/audit/events",
            headers=admin,
            params={"action": "alert.acknowledge", "object_id": alert["id"]},
        )
    ).json()["data"]
    assert len(events) == 1

    async with session_factory()() as s:
        with pytest.raises(Exception, match="never deleted"):
            await s.execute(text("DELETE FROM security.alerts WHERE id = :a"), {"a": alert["id"]})
        await s.rollback()
        with pytest.raises(Exception, match="never deleted"):
            await s.execute(
                text("UPDATE security.alerts SET message = 'x' WHERE id = :a"), {"a": alert["id"]}
            )
        await s.rollback()
