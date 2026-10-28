"""What a fetch does and does not do (CREDENTIAL_PROVIDER.md §3, §7, §8, §10 "side effects")."""

from __future__ import annotations

import pytest

from tests.integration.provider.provider_support import (
    caller,
    code,
    create_app,
    fetch,
    grant_fetch,
    token,
)
from tests.integration.rotation.rotation_support import sql
from tests.integration.safes_support import checkout

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_every_fetch_is_audited_with_its_safe_and_never_the_secret(app, client, admin):
    from tests.integration.provider.provider_support import fetchable

    created = await create_app(client, admin)
    safe_id, target, acct = await fetchable(client, admin, created)
    async with caller(app, created.ip) as c:
        headers = await token(c, created)
        ok = await fetch(c, headers, external_ref=target["external_ref"], purpose="ncm_backup")
        missing = await fetch(c, headers, external_ref="monetx-unknown")
    assert ok.status_code == 200 and missing.status_code == 404
    rows = await sql(
        "SELECT actor_id, actor_name, outcome, object_type, safe_id, source_ip, "
        "details::text AS raw, details FROM audit.events WHERE action = 'secret.app_fetch' "
        "AND actor_id = :a ORDER BY seq",
        a=created.id,
    )
    assert [r["outcome"] for r in rows] == ["success", "failure"]
    served, refused = rows
    assert str(served["safe_id"]) == safe_id and served["object_type"] == "account"
    assert served["actor_name"] == f"app:{created.body['app']['name']}"
    assert served["source_ip"] == created.ip
    d = served["details"]
    assert d["purpose"] == "ncm_backup" and d["kind"] == "ssh"
    assert d["account_id"] == acct["id"] and d["target_id"] == target["id"]
    assert d["app_id"] == created.id and d["version_id"] == ok.json()["data"]["version_id"]
    assert refused["details"]["error_code"] == "credential_not_found"
    password = ok.json()["data"]["secret"]["password"]
    assert not [r for r in rows if password in r["raw"] or created.secret in r["raw"]]
    # The app's recent fetches, for the console.
    recent = await client.get(f"/apps/{created.id}/fetches", headers=admin)
    assert [e["outcome"] for e in recent.json()["data"]] == ["failure", "success"]


async def test_fetch_is_not_a_check_out(app, client, admin, make_user):
    """No check-out row, no rotate-after-use job, not blocked by an exclusive check-out."""
    from tests.integration.provider.provider_support import fetchable
    from tests.integration.safes_support import me

    created = await create_app(client, admin)
    safe_id, target, acct = await fetchable(client, admin, created)
    await sql("UPDATE inventory.safes SET rotate_after_use = TRUE WHERE id = :s", s=safe_id)
    holder = await make_user(f"holder{acct['id'][:6]}")
    holder_id = (await me(client, holder))["id"]
    resp = await client.post(
        f"/safes/{safe_id}/members",
        headers=admin,
        json={
            "principal_type": "user",
            "principal_key": holder_id,
            "permissions": ["list", "retrieve"],
        },
    )
    assert resp.status_code == 201, resp.text
    assert (await checkout(client, holder, acct["id"])).status_code == 201  # exclusive
    async with caller(app, created.ip) as c:
        headers = await token(c, created)
        for _ in range(3):
            resp = await fetch(c, headers, external_ref=target["external_ref"])
            assert resp.status_code == 200, resp.text
    checkouts = await sql(
        "SELECT count(*) AS n FROM access.checkouts WHERE account_id = :a", a=acct["id"]
    )
    assert checkouts[0]["n"] == 1  # only the person's
    jobs = await sql(
        "SELECT count(*) AS n FROM access.rotation_jobs WHERE account_id = :a", a=acct["id"]
    )
    assert jobs[0]["n"] == 0


async def test_version_id_changes_when_the_secret_changes(app, client, admin):
    from tests.integration.provider.provider_support import fetchable

    created = await create_app(client, admin)
    _, target, acct = await fetchable(client, admin, created)
    async with caller(app, created.ip) as c:
        headers = await token(c, created)
        first = (await fetch(c, headers, external_ref=target["external_ref"])).json()["data"]
        again = (await fetch(c, headers, external_ref=target["external_ref"])).json()["data"]
        assert first["version_id"] == again["version_id"]
        await client.put(
            f"/accounts/{acct['id']}/secret", headers=admin, json={"value": "Replaced-Pw-9"}
        )
        after = (await fetch(c, headers, external_ref=target["external_ref"])).json()["data"]
    assert after["version_id"] != first["version_id"]
    assert after["secret"] == {"password": "Replaced-Pw-9"}


async def test_version_id_changes_after_a_rotation(app, rotlab, client, admin):
    """A real rotation through the engine (fake device): the fetch serves the new current
    version under a new version_id."""
    created = await create_app(client, admin)
    safe_id = await rotlab.safe()
    await grant_fetch(client, admin, safe_id, created)
    target = await rotlab.target()
    await client.patch(
        f"/targets/{target['id']}", headers=admin, json={"external_ref": f"rot-{target['id']}"}
    )
    acct = await rotlab.account(safe_id=safe_id, target=target)
    ref = f"rot-{target['id']}"
    async with caller(app, created.ip) as c:
        headers = await token(c, created)
        before = (await fetch(c, headers, external_ref=ref)).json()["data"]
        job = await rotlab.request(acct["id"])
        assert (await rotlab.run(job["id"]))["status"] == "succeeded"
        after = (await fetch(c, headers, external_ref=ref)).json()["data"]
    assert after["version_id"] != before["version_id"]
    assert after["secret"]["password"] == await rotlab.current(acct["id"])
    assert after["secret"] != before["secret"]


async def test_snmp_v2c_and_v3_are_stored_and_fetched(app, client, admin):
    from tests.integration.provider.provider_support import account, device, provider_safe

    created = await create_app(client, admin)
    safe_id = await provider_safe(client, admin)
    await grant_fetch(client, admin, safe_id, created)
    v2 = await device(client, admin)
    v3 = await device(client, admin)
    community = {"version": "2c", "community": "c0mmunity-ro"}
    usm = {
        "version": "3",
        "security_name": "monetx",
        "security_level": "authPriv",
        "auth_protocol": "SHA-256",
        "auth_password": "Auth-Pass-123",
        "priv_protocol": "AES",
        "priv_password": "Priv-Pass-456",
    }
    a2 = await account(
        client, admin, v2, safe_id, username="snmp", secret_type="snmp_v2c", snmp=community
    )
    await account(client, admin, v3, safe_id, username="monetx", secret_type="snmp_v3", snmp=usm)
    async with caller(app, created.ip) as c:
        headers = await token(c, created)
        got2 = (await fetch(c, headers, kind="snmp", external_ref=v2["external_ref"])).json()
        got3 = (await fetch(c, headers, kind="snmp", external_ref=v3["external_ref"])).json()
    assert got2["data"]["secret"] == community and got2["data"]["kind"] == "snmp"
    assert got3["data"]["secret"] == usm
    # Sealed as one document in the vault, never in the clear.
    rows = await sql("SELECT ciphertext FROM vault.secrets WHERE owner_id = :a", a=a2["id"])
    assert len(rows) == 1 and b"c0mmunity" not in bytes(rows[0]["ciphertext"])
    # Replacing it takes the structured form too.
    resp = await client.put(
        f"/accounts/{a2['id']}/secret",
        headers=admin,
        json={"snmp": {"version": "2c", "community": "new-community"}},
    )
    assert resp.status_code == 200, resp.text


async def test_snmp_v3_levels_decide_the_fields(app, client, admin):
    from tests.integration.provider.provider_support import account, device, provider_safe

    created = await create_app(client, admin)
    safe_id = await provider_safe(client, admin)
    await grant_fetch(client, admin, safe_id, created)
    target = await device(client, admin)
    auth_only = {
        "version": "3",
        "security_name": "ro",
        "security_level": "authNoPriv",
        "auth_protocol": "SHA",
        "auth_password": "Auth-Pass-123",
    }
    await account(
        client, admin, target, safe_id, username="ro", secret_type="snmp_v3", snmp=auth_only
    )
    async with caller(app, created.ip) as c:
        got = await fetch(
            c, await token(c, created), kind="snmp", external_ref=target["external_ref"]
        )
    assert got.json()["data"]["secret"] == auth_only  # no priv fields at all
    bad = [
        {**auth_only, "priv_protocol": "AES", "priv_password": "Priv-Pass-456"},
        {**auth_only, "security_level": "authPriv"},
        {
            "version": "3",
            "security_name": "x",
            "security_level": "noAuthNoPriv",
            "auth_password": "Auth-Pass-123",
        },
    ]
    for snmp in bad:
        resp = await client.post(
            "/accounts",
            headers=admin,
            json={
                "target_id": target["id"],
                "safe_id": safe_id,
                "username": "bad",
                "secret_type": "snmp_v3",
                "snmp": snmp,
            },
        )
        assert resp.status_code == 422, resp.text
    mixed = await client.post(
        "/accounts",
        headers=admin,
        json={
            "target_id": target["id"],
            "safe_id": safe_id,
            "username": "mixed",
            "secret_type": "snmp_v2c",
            "secret": "plain-community",
        },
    )
    assert mixed.status_code == 422 and code(mixed) == "invalid_snmp_secret"
    wrong_version = await client.post(
        "/accounts",
        headers=admin,
        json={
            "target_id": target["id"],
            "safe_id": safe_id,
            "username": "wv",
            "secret_type": "snmp_v2c",
            "snmp": auth_only,
        },
    )
    assert wrong_version.status_code == 422


async def test_rotation_refuses_snmp_accounts_with_a_clear_reason(rotlab, client, admin):
    safe_id = await rotlab.safe()
    target = await rotlab.target()
    resp = await client.post(
        "/accounts",
        headers=admin,
        json={
            "target_id": target["id"],
            "safe_id": safe_id,
            "username": "snmp",
            "secret_type": "snmp_v2c",
            "snmp": {"version": "2c", "community": "public-ro"},
        },
    )
    assert resp.status_code == 201, resp.text
    refused = await client.post(
        f"/accounts/{resp.json()['data']['id']}/rotate",
        headers=admin,
        json={"reason": "provider test"},
    )
    assert refused.status_code == 409, refused.text
    assert "SNMP credentials" in refused.json()["error"]["message"]
