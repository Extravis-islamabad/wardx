"""Directory sync, as one story on a shared mock directory (tests run in file order)."""

from __future__ import annotations

import ldap3
import pytest
from sqlalchemy import text

from src.core.db import session_factory
from src.services import directory_service
from tests.integration.test_directory import CONFIG
from tests.ldap_mock import ADMINS, BASE, SVC_DN, SVC_PW, build_directory, mock_factory

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORDS = {"akhan": "Dir-Pass-akhan1", "bahmed": "Dir-Pass-bahmed1", "smalik": "Dir-Pass-smalik1"}
state: dict = {}


@pytest.fixture(scope="module")
async def ad(client, admin):
    server = build_directory()
    directory_service.set_connection_factory(mock_factory(server))
    resp = await client.put(
        "/directory", headers=admin, json={**CONFIG, "sync_interval_minutes": 0}
    )
    assert resp.status_code == 200, resp.text
    yield server
    await client.put("/directory", headers=admin, json={**CONFIG, "enabled": False})
    directory_service.set_connection_factory(directory_service.default_connection)


def _svc(server) -> ldap3.Connection:
    conn = ldap3.Connection(server, user=SVC_DN, password=SVC_PW, client_strategy=ldap3.MOCK_SYNC)
    conn.bind()
    return conn


async def _login(client, username: str):
    return await client.post(
        "/auth/login", json={"username": username, "password": PASSWORDS[username]}
    )


async def _sync(client, admin, **body):
    resp = await client.post("/directory/sync", headers=admin, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _user(client, admin, username: str) -> dict:
    rows = (await client.get("/users", headers=admin, params={"search": username})).json()["data"]
    return next(u for u in rows if u["username"] == username)


async def test_setup_users_sign_in_and_one_holds_a_checkout(client, admin, ad):
    async with session_factory()() as s:
        # Clean slate for users earlier test files may have touched.
        await s.execute(
            text(
                "UPDATE iam.users SET is_active = TRUE, disabled_reason = NULL, failed_logins = 0, "
                "locked_until = NULL WHERE auth_source = 'ldap'"
            )
        )
        await s.commit()
    for name in PASSWORDS:
        resp = await _login(client, name)
        assert resp.status_code == 200, resp.text
        state[name] = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}

    target = (
        await client.post(
            "/targets",
            headers=admin,
            json={
                "name": "sync-box",
                "address": "10.9.9.9",
                "platform": "linux",
                "protocol": "ssh",
            },
        )
    ).json()["data"]
    account = (
        await client.post(
            "/accounts",
            headers=admin,
            json={"target_id": target["id"], "username": "root", "secret": "Sync-Box-Secret-1"},
        )
    ).json()["data"]
    co = await client.post(
        "/checkouts",
        headers=state["bahmed"],
        json={"account_id": account["id"], "reason": "maintenance"},
    )
    assert co.status_code == 201, co.text
    state["checkout"] = co.json()["data"]["id"]
    # A live gateway session row for the same user (as the gateway would write it).
    async with session_factory()() as s:
        state["session"] = (
            await s.execute(
                text(
                    "INSERT INTO access.sessions (user_id, account_username, target_name, "
                    "target_address, protocol, status) SELECT id, 'root', 'sync-box', '10.9.9.9', "
                    "'ssh', 'active' FROM iam.users WHERE username = 'bahmed' RETURNING id"
                )
            )
        ).scalar_one()
        await s.commit()


async def test_clean_run_changes_nothing(client, admin, ad):
    result = await _sync(client, admin)
    assert result["status"] == "ok" and result["disabled"] == [] and result["checked"] >= 3


async def test_preview_shows_a_leaver_without_touching_them(client, admin, ad):
    _svc(ad).delete(f"cn=Bilal Ahmed,ou=people,{BASE}")
    await client.put("/directory", headers=admin, json={**CONFIG, "sync_max_disable_percent": 100})
    result = await _sync(client, admin, dry_run=True)
    assert (
        result["dry_run"]
        and {"username": "bahmed", "reason": "not in directory"} in result["disabled"]
    )
    assert (await client.get("/auth/me", headers=state["bahmed"])).status_code == 200


async def test_leaver_is_disabled_and_cut_off_at_once(client, admin, ad):
    result = await _sync(client, admin)
    assert result["status"] == "ok"
    assert [d["username"] for d in result["disabled"]] == ["bahmed"]
    assert result["revoked_checkouts"] == 1 and result["killed_sessions"] == 1
    async with session_factory()() as s:
        kill = (
            await s.execute(
                text(
                    "SELECT terminate_requested_at, close_reason FROM access.sessions WHERE id = :i"
                ),
                {"i": state["session"]},
            )
        ).one()
    # The gateway shows this reason in the user's terminal when it disconnects them.
    assert kill.terminate_requested_at is not None
    assert kill.close_reason == "Access removed: you are no longer in the directory"

    # Their existing token stops working, their check-out is revoked, they cannot sign in.
    assert (await client.get("/auth/me", headers=state["bahmed"])).status_code == 401
    mine = (await client.get("/checkouts", headers=admin, params={"page_size": 100})).json()
    status = next(c["status"] for c in mine["data"] if c["id"] == state["checkout"])
    assert status == "revoked"
    assert (await _login(client, "bahmed")).status_code == 401
    assert (await _user(client, admin, "bahmed"))["is_active"] is False


async def test_role_change_applies_without_sign_in(client, admin, ad):
    _svc(ad).modify(
        f"cn=Sara Malik,ou=people,{BASE}", {"memberOf": [(ldap3.MODIFY_REPLACE, [ADMINS])]}
    )
    result = await _sync(client, admin)
    assert {"username": "smalik", "from": "auditor", "to": "admin"} in result["role_changes"]
    assert (await _user(client, admin, "smalik"))["role"] == "admin"
    # The old token carried the old role: it no longer works.
    assert (await client.get("/auth/me", headers=state["smalik"])).status_code == 401


async def test_mass_disable_stops_for_review_then_force_applies(client, admin, ad):
    # Re-add the leaver so this run starts from three active users.
    _svc(ad).strategy.add_entry(
        f"cn=Bilal Ahmed,ou=people,{BASE}",
        {
            "objectClass": ["user"],
            "sAMAccountName": "bahmed",
            "userPassword": PASSWORDS["bahmed"],
            "displayName": "Bilal Ahmed",
            "memberOf": [ADMINS],
        },
    )
    back = await _sync(client, admin)
    assert back["enabled"] == ["bahmed"]  # sync disabled them, so sync brings them back

    await client.put("/directory", headers=admin, json={**CONFIG, "sync_max_disable_percent": 20})
    svc = _svc(ad)
    for cn in ("Ayesha Khan", "Sara Malik"):
        svc.delete(f"cn={cn},ou=people,{BASE}")
    held = await _sync(client, admin)
    assert held["status"] == "needs_review" and "over the 20% limit" in held["problems"][0]
    assert (await _user(client, admin, "akhan"))["is_active"] is True  # nothing changed

    forced = await _sync(client, admin, force=True)
    assert forced["status"] == "ok"
    assert {d["username"] for d in forced["disabled"]} == {"akhan", "smalik"}


async def test_admin_disabled_user_is_not_re_enabled(client, admin, ad):
    user = await _user(client, admin, "bahmed")
    await client.patch(f"/users/{user['id']}", headers=admin, json={"is_active": False})
    result = await _sync(client, admin)
    assert "bahmed" not in result["enabled"]
    assert (await _user(client, admin, "bahmed"))["is_active"] is False


async def test_ambiguous_entries_are_reported_not_disabled(client, admin, ad):
    async with session_factory()() as s:
        await s.execute(
            text(
                "INSERT INTO iam.users (username, password_hash, role, auth_source) "
                "VALUES ('dupe', '!directory', 'user', 'ldap') ON CONFLICT DO NOTHING"
            )
        )
        await s.commit()
    result = await _sync(client, admin)
    assert "dupe" not in [d["username"] for d in result["disabled"]]
    assert any("dupe: several directory entries" in p for p in result["problems"])


async def test_unreachable_directory_changes_nothing(client, admin, ad):
    def broken(*_):
        raise ldap3.core.exceptions.LDAPSocketOpenError("connection refused")

    directory_service.set_connection_factory(broken)
    try:
        result = await _sync(client, admin)
    finally:
        directory_service.set_connection_factory(mock_factory(ad))
    assert result["status"] == "failed" and result["disabled"] == []
    cfg = (await client.get("/directory", headers=admin)).json()["data"]
    assert cfg["last_sync_status"] == "failed"
