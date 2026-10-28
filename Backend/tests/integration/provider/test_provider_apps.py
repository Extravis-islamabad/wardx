"""Application identity management (CREDENTIAL_PROVIDER.md §1, §3, §9): apps.manage only,
secrets shown once and stored only as hashes, two active at most, every change audited,
and app safe members that hold exactly 'fetch'."""

from __future__ import annotations

import pytest

from tests.integration.provider.provider_support import (
    caller,
    code,
    create_app,
    grant_fetch,
    provider_safe,
)
from tests.integration.rotation.rotation_support import one, sql
from tests.integration.safes_support import tag

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_only_apps_manage_holders_manage_apps(client, admin, make_user):
    user = await make_user(f"noapps{tag()}")
    assert (await client.get("/apps", headers=user)).status_code == 403
    resp = await client.post("/apps", headers=user, json={"name": f"x-{tag()}"})
    assert resp.status_code == 403
    assert (await client.get("/apps", headers=admin)).status_code == 200


async def test_secret_is_shown_once_and_stored_only_as_a_hash(client, admin):
    app = await create_app(client, admin)
    assert app.secret.startswith("wxs_") and app.client_id.startswith("wxa_")
    got = (await client.get(f"/apps/{app.id}", headers=admin)).json()["data"]
    assert app.secret not in str(got)
    [secret] = got["secrets"]
    assert secret["status"] == "active" and app.secret.startswith(secret["prefix"])
    row = await one("SELECT secret_hash FROM iam.app_secrets WHERE app_id = :a", a=app.id)
    assert row["secret_hash"].startswith("$argon2id$") and app.secret not in row["secret_hash"]
    # No audit event carries the secret.
    rows = await sql("SELECT details::text AS d FROM audit.events WHERE object_id = :a", a=app.id)
    assert rows and not [r for r in rows if app.secret in r["d"]]


async def test_two_active_secrets_at_most(client, admin):
    app = await create_app(client, admin)
    second = await client.post(f"/apps/{app.id}/secrets", headers=admin, json={})
    assert second.status_code == 201, second.text
    third = await client.post(f"/apps/{app.id}/secrets", headers=admin, json={})
    assert third.status_code == 409
    first_id = second.json()["data"]["app"]["secrets"][-1]["id"]
    revoked = await client.post(f"/apps/{app.id}/secrets/{first_id}/revoke", headers=admin)
    assert revoked.status_code == 200, revoked.text
    again = await client.post(f"/apps/{app.id}/secrets/{first_id}/revoke", headers=admin)
    assert again.status_code == 409
    assert (await client.post(f"/apps/{app.id}/secrets", headers=admin, json={})).status_code == 201


async def test_a_past_expiry_is_refused(client, admin):
    app = await create_app(client, admin)
    resp = await client.post(
        f"/apps/{app.id}/secrets", headers=admin, json={"expires_at": "2001-01-01T00:00:00Z"}
    )
    assert resp.status_code == 422


async def test_allowlist_is_validated_and_empty_means_unusable(client, admin):
    bad = await client.post(
        "/apps", headers=admin, json={"name": f"bad-{tag()}", "ip_allowlist": ["not-an-ip"]}
    )
    assert bad.status_code == 422
    app = await create_app(client, admin, ip="10.9.8.7")
    assert app.body["app"]["ip_allowlist"] == ["10.9.8.7/32"] and app.body["app"]["usable"]
    resp = await client.patch(f"/apps/{app.id}", headers=admin, json={"ip_allowlist": []})
    assert resp.status_code == 200 and resp.json()["data"]["usable"] is False


async def test_names_are_unique_case_insensitively(client, admin):
    name = f"dup-{tag()}"
    assert (await client.post("/apps", headers=admin, json={"name": name})).status_code == 201
    again = await client.post("/apps", headers=admin, json={"name": name.upper()})
    assert again.status_code == 409


async def test_every_change_is_audited(client, admin):
    app = await create_app(client, admin)
    await client.patch(f"/apps/{app.id}", headers=admin, json={"rate_limit_per_minute": 30})
    await client.patch(f"/apps/{app.id}", headers=admin, json={"enabled": False})
    await client.patch(f"/apps/{app.id}", headers=admin, json={"enabled": True})
    new = (await client.post(f"/apps/{app.id}/secrets", headers=admin, json={})).json()["data"]
    await client.post(f"/apps/{app.id}/secrets/{new['secret_id']}/revoke", headers=admin)
    rows = await sql(
        "SELECT action FROM audit.events WHERE object_type = 'app' AND object_id = :a ORDER BY seq",
        a=app.id,
    )
    assert [r["action"] for r in rows] == [
        "app.create",
        "app.secret_add",
        "app.update",
        "app.disable",
        "app.enable",
        "app.secret_add",
        "app.secret_revoke",
    ]


async def test_app_members_hold_only_fetch(client, admin, make_user):
    app = await create_app(client, admin)
    safe_id = await provider_safe(client, admin)
    for perms in (["list"], ["fetch", "list"], ["retrieve"]):
        resp = await client.post(
            f"/safes/{safe_id}/members",
            headers=admin,
            json={"principal_type": "app", "principal_key": app.id, "permissions": perms},
        )
        assert resp.status_code == 422, (perms, resp.text)
    user = await make_user(f"nofetch{tag()}")
    me = (await client.get("/auth/me", headers=user)).json()["data"]
    resp = await client.post(
        f"/safes/{safe_id}/members",
        headers=admin,
        json={"principal_type": "user", "principal_key": me["id"], "permissions": ["fetch"]},
    )
    assert resp.status_code == 422
    member = await grant_fetch(client, admin, safe_id, app)
    assert member["display_name"] == app.body["app"]["name"]
    change = await client.patch(
        f"/safes/{safe_id}/members/{member['id']}", headers=admin, json={"permissions": ["use"]}
    )
    assert change.status_code == 422
    # The database refuses it too, whatever the API does.
    with pytest.raises(Exception, match="ck_safe_members_app_fetch"):
        await sql(
            "UPDATE inventory.safe_members SET permissions = ARRAY['list'] WHERE id = :m",
            m=member["id"],
        )
    unknown = await client.post(
        f"/safes/{safe_id}/members",
        headers=admin,
        json={
            "principal_type": "app",
            "principal_key": "00000000-0000-0000-0000-00000000abcd",
            "permissions": ["fetch"],
        },
    )
    assert unknown.status_code == 404


async def test_safe_app_fetch_settings_need_manage_members_and_are_audited(
    client, admin, make_user
):
    safe_id = await provider_safe(client, admin)
    got = (await client.get(f"/safes/{safe_id}/app-fetch", headers=admin)).json()["data"]
    assert got["allow_app_fetch"] is False and got["app_cache_seconds"] == 300
    outsider = await make_user(f"outsider{tag()}")
    resp = await client.put(
        f"/safes/{safe_id}/app-fetch", headers=outsider, json={"allow_app_fetch": True}
    )
    assert resp.status_code == 404
    bad = await client.put(
        f"/safes/{safe_id}/app-fetch", headers=admin, json={"app_cache_seconds": 3601}
    )
    assert bad.status_code == 422
    resp = await client.put(
        f"/safes/{safe_id}/app-fetch",
        headers=admin,
        json={"allow_app_fetch": True, "app_cache_seconds": 60},
    )
    assert resp.status_code == 200, resp.text
    event = await one(
        "SELECT details FROM audit.events WHERE action = 'safe.app_fetch_update' AND safe_id = :s",
        s=safe_id,
    )
    assert event["details"]["after"] == {"allow_app_fetch": True, "app_cache_seconds": 60}


async def test_apps_never_sign_in_to_the_console(app, client, admin):
    created = await create_app(client, admin)
    async with caller(app, created.ip) as c:
        resp = await c.post(
            "/auth/login", json={"username": created.client_id, "password": created.secret}
        )
        assert resp.status_code == 401 and code(resp) == "unauthorized"
