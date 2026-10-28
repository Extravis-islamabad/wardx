"""Safe membership through directory groups: the group cache, its expiry and refresh,
fail-closed while the directory is down, sync refresh and clear, and no self-grant
through your own group. Runs against the in-memory AD tree; tests run in file order."""

from __future__ import annotations

import ldap3
import pytest
from sqlalchemy import text

from src.core.db import session_factory
from src.services.directory import directory_service
from tests.integration.safes_support import (
    ALL_PERMS,
    add_member,
    checkout,
    grant,
    me,
    new_account,
    new_safe,
    tag,
)
from tests.integration.test_directory import CONFIG
from tests.ldap_mock import (
    ADMINS,
    AUDITORS,
    BASE,
    OPERATORS,
    SVC_DN,
    SVC_PW,
    build_directory,
    mock_factory,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

GROUP_USER, GROUP_PW = "gmember", "Dir-Pass-gmember1"  # gitleaks:allow
LEAVER, LEAVER_PW = "gleaver", "Dir-Pass-gleaver1"  # gitleaks:allow
NOC_DN = f"cn=Safe NOC,ou=groups,{BASE}"
state: dict = {}


def _svc(server) -> ldap3.Connection:
    conn = ldap3.Connection(server, user=SVC_DN, password=SVC_PW, client_strategy=ldap3.MOCK_SYNC)
    conn.bind()
    return conn


def _person(server, cn: str, sam: str, pw: str, groups: list[str]) -> str:
    dn = f"cn={cn},ou=people,{BASE}"
    _svc(server).strategy.add_entry(
        dn,
        {
            "objectClass": ["user"],
            "sAMAccountName": sam,
            "userPassword": pw,
            "displayName": cn,
            "memberOf": groups,
        },
    )
    return dn


def _broken(*_):
    raise ldap3.core.exceptions.LDAPSocketOpenError("connection refused")


@pytest.fixture(scope="module")
async def ad(client, admin):
    server = build_directory()
    state["dn"] = _person(server, "Group Member", GROUP_USER, GROUP_PW, [OPERATORS, NOC_DN])
    state["leaver_dn"] = _person(server, "Group Leaver", LEAVER, LEAVER_PW, [OPERATORS])
    directory_service.set_connection_factory(mock_factory(server))
    resp = await client.put(
        "/directory", headers=admin, json={**CONFIG, "sync_interval_minutes": 0}
    )
    assert resp.status_code == 200, resp.text
    yield server
    await client.put("/directory", headers=admin, json={**CONFIG, "enabled": False})
    directory_service.set_connection_factory(directory_service.default_connection)


async def _sign_in(client, username: str, password: str) -> dict:
    resp = await client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _cache(user_id: str):
    async with session_factory()() as s:
        return (
            await s.execute(
                text("SELECT groups, fetched_at FROM iam.user_group_cache WHERE user_id = :u"),
                {"u": user_id},
            )
        ).one_or_none()


async def _age_cache(user_id: str, minutes: int = 30) -> None:
    async with session_factory()() as s:
        await s.execute(
            text(
                "UPDATE iam.user_group_cache SET fetched_at = NOW() - make_interval(mins => :m) "
                "WHERE user_id = :u"
            ),
            {"u": user_id, "m": minutes},
        )
        await s.commit()


async def test_setup_group_member_signs_in_and_groups_are_cached(client, admin, ad, make_user):
    headers = await _sign_in(client, GROUP_USER, GROUP_PW)
    user = await me(client, headers)
    cached = await _cache(user["id"])
    assert set(cached.groups) == {OPERATORS.lower(), NOC_DN.lower()}

    safe_id = await new_safe(client, admin)
    keeper = await make_user(f"keeper{tag()}", role="admin")
    await grant(client, admin, safe_id, "user", (await me(client, keeper))["id"], ALL_PERMS)
    account = await new_account(client, keeper, safe_id)
    state.update(headers=headers, user=user, safe_id=safe_id, account=account, keeper=keeper)


async def test_group_membership_grants_access(client, admin, ad):
    url = f"/accounts/{state['account']['id']}"
    assert (await client.get(url, headers=state["headers"])).status_code == 404
    # The DN is stored normalised, whatever case and spacing the admin typed.
    member = await grant(
        client, admin, state["safe_id"], "group", NOC_DN.upper().replace(",", " , "), ["list"]
    )
    assert member["principal_key"] == NOC_DN.lower()
    state["member_id"] = member["id"]
    assert (await client.get(url, headers=state["headers"])).status_code == 200
    assert (await checkout(client, state["headers"], state["account"]["id"])).status_code == 403
    await client.patch(
        f"/safes/{state['safe_id']}/members/{member['id']}",
        headers=admin,
        json={"permissions": ["list", "retrieve"]},
    )
    co = await checkout(client, state["headers"], state["account"]["id"])
    assert co.status_code == 201, co.text
    await client.post(f"/checkouts/{co.json()['data']['id']}/checkin", headers=state["headers"])


async def test_fresh_cache_is_used_and_stale_cache_is_refreshed(client, ad):
    url = f"/accounts/{state['account']['id']}"
    _svc(ad).modify(state["dn"], {"memberOf": [(ldap3.MODIFY_REPLACE, [OPERATORS])]})
    # Within WARDX_GROUP_CACHE_MINUTES the cached groups still count.
    assert (await client.get(url, headers=state["headers"])).status_code == 200

    await _age_cache(state["user"]["id"])
    assert (await client.get(url, headers=state["headers"])).status_code == 404
    cached = await _cache(state["user"]["id"])
    assert set(cached.groups) == {OPERATORS.lower()}

    _svc(ad).modify(state["dn"], {"memberOf": [(ldap3.MODIFY_REPLACE, [OPERATORS, NOC_DN])]})
    await _age_cache(state["user"]["id"])
    assert (await client.get(url, headers=state["headers"])).status_code == 200


async def test_directory_down_fails_closed_for_groups_only(client, admin, ad):
    url = f"/accounts/{state['account']['id']}"
    direct_safe = await new_safe(client, admin)
    keeper_id = (await me(client, state["keeper"]))["id"]
    await grant(client, admin, direct_safe, "user", keeper_id, ALL_PERMS)
    direct_account = await new_account(client, state["keeper"], direct_safe)
    await grant(client, admin, direct_safe, "user", state["user"]["id"], ["list"])

    await _age_cache(state["user"]["id"])
    directory_service.set_connection_factory(_broken)
    try:
        assert (await client.get(url, headers=state["headers"])).status_code == 404
        # Direct membership keeps working.
        direct = await client.get(f"/accounts/{direct_account['id']}", headers=state["headers"])
        assert direct.status_code == 200
        cfg = (await client.get("/directory", headers=admin)).json()["data"]
        assert cfg["reachable"] is False and "connection refused" in cfg["reachability_error"]
    finally:
        directory_service.set_connection_factory(mock_factory(ad))

    # Within the retry window WardX does not try again; a successful contact
    # (here the admin's test lookup) ends it.
    assert (await client.get(url, headers=state["headers"])).status_code == 404
    resp = await client.post("/directory/test", headers=admin, json={"username": GROUP_USER})
    assert resp.status_code == 200
    assert (await client.get("/directory", headers=admin)).json()["data"]["reachable"] is True
    assert (await client.get(url, headers=state["headers"])).status_code == 200


async def test_no_self_grant_through_your_own_group(client, admin, ad):
    akhan = await _sign_in(client, "akhan", "Dir-Pass-akhan1")  # gitleaks:allow
    for dn in (OPERATORS, ADMINS):
        resp = await add_member(client, akhan, state["safe_id"], "group", dn, ["list"])
        assert resp.status_code == 403, resp.text
        assert resp.json()["error"]["code"] == "self_grant_forbidden"
    # A group akhan is not in is fine.
    resp = await add_member(client, akhan, state["safe_id"], "group", AUDITORS, ["list"])
    assert resp.status_code == 201, resp.text

    # Directory down: akhan's groups can't be verified, so group grants are refused.
    await _age_cache((await me(client, akhan))["id"], minutes=60)
    directory_service.set_connection_factory(_broken)
    try:
        resp = await add_member(
            client, akhan, state["safe_id"], "group", f"cn=x{tag()},{BASE}", ["list"]
        )
        assert resp.json()["error"]["code"] == "self_grant_forbidden"
    finally:
        directory_service.set_connection_factory(mock_factory(ad))
        await client.post("/directory/test", headers=admin, json={"username": "akhan"})


async def test_sync_refreshes_the_cache_and_clears_it_for_disabled_users(client, admin, ad):
    leaver = await me(client, await _sign_in(client, LEAVER, LEAVER_PW))
    assert await _cache(leaver["id"]) is not None

    await _age_cache(state["user"]["id"])
    _svc(ad).modify(state["dn"], {"memberOf": [(ldap3.MODIFY_REPLACE, [AUDITORS, NOC_DN])]})
    _svc(ad).delete(state["leaver_dn"])
    resp = await client.post("/directory/sync", headers=admin, json={"force": True})
    assert resp.status_code == 200, resp.text
    assert LEAVER in [d["username"] for d in resp.json()["data"]["disabled"]]

    cached = await _cache(state["user"]["id"])
    assert set(cached.groups) == {AUDITORS.lower(), NOC_DN.lower()}
    assert await _cache(leaver["id"]) is None
