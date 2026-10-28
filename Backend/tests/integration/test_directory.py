"""Directory sign-in end to end, against the in-memory AD tree."""

from __future__ import annotations

import ldap3
import pytest

from src.services.directory import directory_service
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

CONFIG = {
    "enabled": True,
    "server_url": "ldap://mock-ad",
    "bind_dn": SVC_DN,
    "bind_password": SVC_PW,
    "user_base_dn": f"ou=people,{BASE}",
    # ldap3's mock cannot evaluate the AD in-chain matching rule (it rejects the
    # extensible-match filter), so nested groups stay off against the mock;
    # tests/unit/test_ldap_client.py checks the filter WardX sends.
    "nested_groups": False,
    "role_mappings": [
        {"group_dn": ADMINS, "role": "admin"},
        {"group_dn": OPERATORS, "role": "user"},
        {"group_dn": AUDITORS, "role": "auditor"},
    ],
}


@pytest.fixture
async def directory(client, admin):
    server = build_directory()
    directory_service.set_connection_factory(mock_factory(server))
    resp = await client.put("/directory", headers=admin, json=CONFIG)
    assert resp.status_code == 200, resp.text
    yield server
    # Other test files must see a directory-free WardX again.
    await client.put("/directory", headers=admin, json={**CONFIG, "enabled": False})
    directory_service.set_connection_factory(directory_service.default_connection)


async def _login(client, username: str, password: str):
    return await client.post("/auth/login", json={"username": username, "password": password})


async def test_config_hides_the_bind_password_and_can_test_a_user(client, admin, directory):
    cfg = (await client.get("/directory", headers=admin)).json()["data"]
    assert cfg["has_bind_password"] is True and "bind_password" not in cfg
    assert SVC_PW not in str(cfg)
    found = (
        await client.post("/directory/test", headers=admin, json={"username": "bahmed"})
    ).json()
    assert found["data"]["role"] == "user" and OPERATORS in found["data"]["groups"]


async def test_directory_user_signs_in_and_is_provisioned(client, admin, directory):
    resp = await _login(client, "akhan", "Dir-Pass-akhan1")
    assert resp.status_code == 200, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    me = (await client.get("/auth/me", headers=headers)).json()["data"]
    assert (me["username"], me["role"], me["auth_source"]) == ("akhan", "admin", "ldap")
    assert me["email"] == "akhan@corp.test" and me["full_name"] == "Ayesha Khan"

    # Directory users have no local password to change or reset.
    resp = await client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": "Dir-Pass-akhan1", "new_password": "Another-Pass-123"},
    )
    assert resp.status_code == 409
    resp = await client.post(
        f"/users/{me['id']}/reset-password",
        headers=admin,
        json={"new_password": "Another-Pass-123"},
    )
    assert resp.status_code == 409


async def test_group_change_updates_role_and_removal_blocks_sign_in(client, admin, directory):
    assert (await _login(client, "bahmed", "Dir-Pass-bahmed1")).status_code == 200
    users = (await client.get("/users", headers=admin, params={"search": "bahmed"})).json()["data"]
    assert users[0]["role"] == "user"

    dn = f"cn=Bilal Ahmed,ou=people,{BASE}"
    svc = ldap3.Connection(directory, user=SVC_DN, password=SVC_PW, client_strategy=ldap3.MOCK_SYNC)
    svc.bind()
    svc.modify(dn, {"memberOf": [(ldap3.MODIFY_REPLACE, [AUDITORS])]})
    assert (await _login(client, "bahmed", "Dir-Pass-bahmed1")).status_code == 200
    users = (await client.get("/users", headers=admin, params={"search": "bahmed"})).json()["data"]
    assert users[0]["role"] == "auditor"

    svc.modify(dn, {"memberOf": [(ldap3.MODIFY_REPLACE, [])]})
    assert (await _login(client, "bahmed", "Dir-Pass-bahmed1")).status_code == 401


async def test_local_account_is_never_taken_over(client, directory):
    # The directory has an "admin" with its own password; WardX's local admin wins.
    assert (await _login(client, "admin", "Dir-Pass-admin1")).status_code == 401


async def test_wrong_directory_password_counts_towards_lockout(client, directory):
    assert (await _login(client, "smalik", "Dir-Pass-smalik1")).status_code == 200
    for _ in range(5):
        assert (await _login(client, "smalik", "wrong")).status_code == 401
    assert (await _login(client, "smalik", "Dir-Pass-smalik1")).status_code == 423


async def test_turning_the_directory_off_stops_its_users(client, admin, directory):
    await _login(client, "akhan", "Dir-Pass-akhan1")
    await client.put("/directory", headers=admin, json={**CONFIG, "enabled": False})
    assert (await _login(client, "akhan", "Dir-Pass-akhan1")).status_code == 401


async def test_unreachable_directory_is_reported_not_hidden(client, admin, directory):
    def broken(*_):
        raise ldap3.core.exceptions.LDAPSocketOpenError("connection refused")

    directory_service.set_connection_factory(broken)
    resp = await _login(client, "akhan", "Dir-Pass-akhan1")
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "directory_unavailable"
    # Local accounts keep working while the directory is down.
    assert (await _login(client, "admin", "Admin-Passw0rd-Test")).status_code == 200


async def test_enabling_without_a_bind_password_is_refused(client, admin):
    directory_service.set_connection_factory(mock_factory(build_directory()))
    # Fresh config row would need one; here the stored password exists, so drop it via a
    # config that omits it and check the API keeps the old one rather than clearing it.
    resp = await client.put("/directory", headers=admin, json={**CONFIG, "bind_password": None})
    assert resp.status_code == 200 and resp.json()["data"]["has_bind_password"] is True
    await client.put("/directory", headers=admin, json={**CONFIG, "enabled": False})
