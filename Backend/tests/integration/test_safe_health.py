"""Safe health (healthy / break_glass_only / unreachable), break-glass coverage, and the
dashboard warning while the directory is unreachable. Tests run in file order."""

from __future__ import annotations

import ldap3
import pytest

from src.services.directory import directory_service
from tests.integration.safes_support import grant, me, new_safe, tag
from tests.integration.test_break_glass import EMERGENCY, make_holder
from tests.integration.test_directory import CONFIG
from tests.ldap_mock import BASE, SVC_DN, SVC_PW, build_directory, mock_factory

pytestmark = pytest.mark.asyncio(loop_scope="session")

GROUP_DN = f"cn=Health Group,ou=groups,{BASE}"
state: dict = {}


async def _attention(client, headers) -> dict:
    resp = await client.get("/dashboard/attention", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _health(client, admin, safe_id: str) -> str:
    report = (await client.get("/safes/health", headers=admin)).json()["data"]
    return next(s["state"] for s in report["safes"] if s["safe_id"] == safe_id)


async def _coverage(client, admin) -> dict:
    return (await _attention(client, admin))["break_glass"]


async def test_coverage_warns_at_zero_and_one_and_clears_at_two(client, admin, make_user):
    # Start from no holders: revoke (never delete) every current grant.
    users = (await client.get("/users", headers=admin, params={"page_size": 200})).json()["data"]
    for u in users:
        if EMERGENCY in u["direct_permissions"]:
            resp = await client.delete(f"/users/{u['id']}/permissions/{EMERGENCY}", headers=admin)
            assert resp.status_code == 200, resp.text

    cov = await _coverage(client, admin)
    assert (cov["eligible_holders"], cov["warning"]) == (0, True)
    assert cov["message"].startswith("0 eligible") and "Nobody" in cov["message"]

    # A group-only safe with nobody to break glass: critical.
    safe_id = await new_safe(client, admin)
    await grant(client, admin, safe_id, "group", GROUP_DN, ["list", "retrieve"])
    state["safe_id"] = safe_id
    assert await _health(client, admin, safe_id) == "unreachable"
    listed = (await client.get("/safes", headers=admin, params={"search": ""})).json()["data"]
    attention = await _attention(client, admin)
    flagged = {s["safe_id"]: s for s in attention["safes_needing_attention"]}
    assert flagged[safe_id]["severity"] == "critical"
    assert all(s["health"] for s in listed if s["is_active"])

    state["h1"] = await make_holder(client, admin, make_user)
    cov = await _coverage(client, admin)
    assert (cov["eligible_holders"], cov["warning"]) == (1, True)
    assert "single point of failure" in cov["message"]
    # Break-glass makes a group-only safe a warning, never healthy.
    assert await _health(client, admin, safe_id) == "break_glass_only"
    attention = await _attention(client, admin)
    flagged = {s["safe_id"]: s for s in attention["safes_needing_attention"]}
    assert flagged[safe_id]["severity"] == "warning"

    state["h2"] = await make_holder(client, admin, make_user)
    cov = await _coverage(client, admin)
    assert (cov["eligible_holders"], cov["warning"], cov["message"]) == (2, False, None)


async def test_mfa_reset_of_one_of_two_holders_brings_the_warning_back(client, admin):
    resp = await client.post(f"/users/{state['h2']['user']['id']}/mfa/reset", headers=admin)
    assert resp.status_code == 200
    cov = await _coverage(client, admin)
    assert (cov["eligible_holders"], cov["warning"]) == (1, True)


async def test_direct_user_and_role_members_make_a_safe_healthy(client, admin, make_user):
    safe_id = state["safe_id"]
    user = await me(client, await make_user(f"hm{tag()}"))
    member = await grant(client, admin, safe_id, "user", user["id"], ["list"])
    assert await _health(client, admin, safe_id) == "healthy"
    flagged = {s["safe_id"] for s in (await _attention(client, admin))["safes_needing_attention"]}
    assert safe_id not in flagged

    await client.delete(f"/safes/{safe_id}/members/{member['id']}", headers=admin)
    assert await _health(client, admin, safe_id) == "break_glass_only"
    await make_user(f"hr{tag()}", role="auditor")  # the role has an active user
    role = await grant(client, admin, safe_id, "role", "auditor", ["list"])
    assert await _health(client, admin, safe_id) == "healthy"
    await client.delete(f"/safes/{safe_id}/members/{role['id']}", headers=admin)

    # The last eligible holder disabled: nobody can break glass, the safe is critical.
    await client.patch(
        f"/users/{state['h1']['user']['id']}", headers=admin, json={"is_active": False}
    )
    assert await _health(client, admin, safe_id) == "unreachable"
    assert (await _coverage(client, admin))["eligible_holders"] == 0


async def test_health_api_is_gated(client, make_user):
    plain = await make_user(f"hp{tag()}")
    assert (await client.get("/safes/health", headers=plain)).status_code == 403
    assert (await client.get("/dashboard/attention", headers=plain)).status_code == 403
    auditor = await make_user(f"ha{tag()}", role="auditor")
    assert (await client.get("/dashboard/attention", headers=auditor)).status_code == 200
    rows = (await client.get("/safes", headers=auditor)).json()["data"]
    assert all(r["health"] is None for r in rows)


async def test_directory_outage_lists_safes_nobody_can_reach(client, admin, make_user):
    server = build_directory()
    seed = ldap3.Connection(server, user=SVC_DN, password=SVC_PW, client_strategy=ldap3.MOCK_SYNC)
    seed.strategy.add_entry(
        f"cn=Health Dir,ou=people,{BASE}",
        {
            "objectClass": ["user"],
            "sAMAccountName": "hdir",
            "userPassword": "Dir-Pass-hdir1",  # gitleaks:allow
            "displayName": "Health Dir",
            "memberOf": [CONFIG["role_mappings"][1]["group_dn"]],
        },
    )
    directory_service.set_connection_factory(mock_factory(server))
    assert (await client.put("/directory", headers=admin, json=CONFIG)).status_code == 200
    try:
        login = await client.post(
            "/auth/login", json={"username": "hdir", "password": "Dir-Pass-hdir1"}
        )
        assert login.status_code == 200, login.text
        directory_user = await me(
            client, {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
        )
        group_only = state["safe_id"]
        local_safe = await new_safe(client, admin)
        local_user = await me(client, await make_user(f"hl{tag()}"))
        await grant(client, admin, local_safe, "user", local_user["id"], ["list"])
        directory_safe = await new_safe(client, admin)
        await grant(client, admin, directory_safe, "user", directory_user["id"], ["list"])

        directory = (await _attention(client, admin))["directory"]
        assert directory["reachable"] is True and directory["affected_safes"] == []

        def broken(*_):
            raise ldap3.core.exceptions.LDAPSocketOpenError("connection refused")

        directory_service.set_connection_factory(broken)
        failed = await client.post(
            "/auth/login", json={"username": "hdir", "password": "Dir-Pass-hdir1"}
        )
        assert failed.status_code == 502
        directory = (await _attention(client, admin))["directory"]
        assert directory["unreachable"] is True and "connection refused" in directory["error"]
        affected = {s["safe_id"] for s in directory["affected_safes"]}
        # Group-only and directory-user-only safes are cut off; a local member keeps access.
        assert {group_only, directory_safe} <= affected and local_safe not in affected

        directory_service.set_connection_factory(mock_factory(server))
        await client.post("/directory/test", headers=admin, json={"username": "hdir"})
        directory = (await _attention(client, admin))["directory"]
        assert directory["unreachable"] is False and directory["affected_safes"] == []
    finally:
        await client.put("/directory", headers=admin, json={**CONFIG, "enabled": False})
        directory_service.set_connection_factory(directory_service.default_connection)
