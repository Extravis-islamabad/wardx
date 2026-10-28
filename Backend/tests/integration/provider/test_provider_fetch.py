"""Fetching credentials (CREDENTIAL_PROVIDER.md §3–§5, §7, §10 "fetch")."""

from __future__ import annotations

import pytest

from tests.integration.provider.provider_support import (
    DEVICE_PASSWORD,
    account,
    caller,
    code,
    create_app,
    device,
    fetch,
    fetchable,
    grant_fetch,
    provider_safe,
    token,
)
from tests.integration.rotation.rotation_support import sql

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_fetch_by_external_ref_address_name_and_account_id(app, client, admin):
    created = await create_app(client, admin)
    _, target, acct = await fetchable(client, admin, created)
    async with caller(app, created.ip) as c:
        headers = await token(c, created)
        by_ref = await fetch(c, headers, external_ref=target["external_ref"])
        assert by_ref.status_code == 200, by_ref.text
        assert by_ref.headers["cache-control"] == "no-store"
        data = by_ref.json()["data"]
        assert data["secret"] == {"password": DEVICE_PASSWORD}
        assert data["kind"] == "ssh" and data["username"] == "netadmin"
        assert data["account_id"] == acct["id"] and data["max_cache_seconds"] == 300
        assert data["target"]["external_ref"] == target["external_ref"]
        assert data["version_id"].startswith("cv_")
        for query in ({"address": target["address"]}, {"name": target["name"].upper()}):
            resp = await fetch(c, headers, **query)
            assert resp.status_code in (200, 409), resp.text  # addresses may repeat in tests
        by_id = await c.post(
            f"/provider/credentials/{acct['id']}/fetch", headers=headers, json={"purpose": "poll"}
        )
        assert by_id.status_code == 200 and by_id.json()["data"]["version_id"] == data["version_id"]


async def test_only_safes_where_the_app_holds_fetch(app, client, admin):
    created = await create_app(client, admin)
    other = await create_app(client, admin)
    _, target, acct = await fetchable(client, admin, other)
    # A safe without any app member, and the other app's safe: both read as not found.
    plain_safe = await provider_safe(client, admin)
    plain_target = await device(client, admin)
    plain = await account(client, admin, plain_target, plain_safe)
    async with caller(app, created.ip) as c:
        headers = await token(c, created)
        for ref in (target["external_ref"], plain_target["external_ref"], "monetx-no-such"):
            resp = await fetch(c, headers, external_ref=ref)
            assert resp.status_code == 404 and code(resp) == "credential_not_found", ref
        for account_id in (acct["id"], plain["id"]):
            resp = await c.post(
                f"/provider/credentials/{account_id}/fetch",
                headers=headers,
                json={"purpose": "poll"},
            )
            assert resp.status_code == 404 and code(resp) == "credential_not_found"


async def test_ambiguous_match_needs_a_username(app, client, admin):
    created = await create_app(client, admin)
    safe_id, target, _ = await fetchable(client, admin, created)
    await account(client, admin, target, safe_id, username="backup", secret="Backup-Pw-123")
    async with caller(app, created.ip) as c:
        headers = await token(c, created)
        resp = await fetch(c, headers, external_ref=target["external_ref"])
        assert resp.status_code == 409 and code(resp) == "credential_ambiguous"
        resp = await fetch(c, headers, external_ref=target["external_ref"], username="backup")
        assert resp.status_code == 200 and resp.json()["data"]["username"] == "backup"


async def test_kind_selects_the_secret_type(app, client, admin):
    created = await create_app(client, admin)
    safe_id, target, _ = await fetchable(client, admin, created)
    await account(
        client, admin, target, safe_id, username="en", secret_type="enable_secret", secret="En-1x"
    )
    await account(
        client, admin, target, safe_id, username="api", secret_type="api_key", secret="tok-9"
    )
    ref = target["external_ref"]
    async with caller(app, created.ip) as c:
        headers = await token(c, created)
        enable = (await fetch(c, headers, kind="enable", external_ref=ref)).json()["data"]
        api = (await fetch(c, headers, kind="api", external_ref=ref)).json()["data"]
        snmp = await fetch(c, headers, kind="snmp", external_ref=ref)
    assert enable["secret"] == {"password": "En-1x"} and enable["kind"] == "enable"
    assert api["secret"] == {"token": "tok-9"}
    assert snmp.status_code == 404


async def test_approval_required_safe_refuses_apps_unless_allowed(app, client, admin):
    created = await create_app(client, admin)
    safe_id, target, _ = await fetchable(client, admin, created)
    await sql("UPDATE inventory.safes SET approval_required = TRUE WHERE id = :s", s=safe_id)
    async with caller(app, created.ip) as c:
        headers = await token(c, created)
        resp = await fetch(c, headers, external_ref=target["external_ref"])
        assert resp.status_code == 409
        assert code(resp) == "credential_unavailable.approval_required"
        await client.put(
            f"/safes/{safe_id}/app-fetch",
            headers=admin,
            json={"allow_app_fetch": True, "app_cache_seconds": 45},
        )
        resp = await fetch(c, headers, external_ref=target["external_ref"])
        assert resp.status_code == 200 and resp.json()["data"]["max_cache_seconds"] == 45


@pytest.mark.parametrize(
    ("setup", "expected"),
    [
        (
            "UPDATE inventory.accounts SET sync_status = 'verify_untrustworthy' WHERE id = :a",
            "credential_unavailable.verify_untrustworthy",
        ),
        (
            "UPDATE inventory.accounts SET rotation_status = 'needs_attention' WHERE id = :a",
            "credential_unavailable.rotation_needs_attention",
        ),
        (
            "UPDATE inventory.accounts SET risk_flags = ARRAY['high_risk_empty_password'] "
            "WHERE id = :a",
            "credential_unavailable.no_secret",
        ),
        (
            "UPDATE inventory.accounts SET secret_version = 0 WHERE id = :a",
            "credential_unavailable.no_secret",
        ),
    ],
)
async def test_unavailable_accounts_are_refused_with_their_reason(
    app, client, admin, setup, expected
):
    created = await create_app(client, admin)
    _, target, acct = await fetchable(client, admin, created)
    await sql(setup, a=acct["id"])
    async with caller(app, created.ip) as c:
        headers = await token(c, created)
        resp = await fetch(c, headers, external_ref=target["external_ref"])
    assert resp.status_code == 409 and code(resp) == expected
    event = await sql(
        "SELECT outcome, safe_id, details->>'error_code' AS err FROM audit.events "
        "WHERE action = 'secret.app_fetch' AND object_id = :a",
        a=acct["id"],
    )
    assert [(e["outcome"], e["err"]) for e in event] == [("failure", expected)]
    assert event[0]["safe_id"] is not None


async def test_open_needs_attention_job_refuses_too(app, client, admin):
    created = await create_app(client, admin)
    _, target, acct = await fetchable(client, admin, created)
    await sql(
        "INSERT INTO access.rotation_jobs (account_id, target_id, reason, status) "
        "VALUES (:a, :t, 'manual', 'needs_attention')",
        a=acct["id"],
        t=target["id"],
    )
    async with caller(app, created.ip) as c:
        resp = await fetch(c, await token(c, created), external_ref=target["external_ref"])
    assert code(resp) == "credential_unavailable.rotation_needs_attention"


async def test_inactive_safe_or_target_is_not_found(app, client, admin):
    created = await create_app(client, admin)
    safe_id, target, _ = await fetchable(client, admin, created)
    async with caller(app, created.ip) as c:
        headers = await token(c, created)
        await client.patch(f"/safes/{safe_id}", headers=admin, json={"is_active": False})
        resp = await fetch(c, headers, external_ref=target["external_ref"])
        assert code(resp) == "credential_not_found"
        await client.patch(f"/safes/{safe_id}", headers=admin, json={"is_active": True})
        await sql("UPDATE inventory.targets SET is_active = FALSE WHERE id = :t", t=target["id"])
        resp = await fetch(c, headers, external_ref=target["external_ref"])
        assert code(resp) == "credential_not_found"


async def test_target_query_needs_exactly_one_key(app, client, admin):
    created = await create_app(client, admin)
    async with caller(app, created.ip) as c:
        headers = await token(c, created)
        both = await fetch(c, headers, external_ref="a", name="b")
        none = await c.post(
            "/provider/credentials/fetch",
            headers=headers,
            json={"target": {}, "kind": "ssh", "purpose": "poll"},
        )
        bad_kind = await fetch(c, headers, kind="telnet", external_ref="a")
        bad_purpose = await fetch(c, headers, purpose="steal", external_ref="a")
    for resp in (both, none, bad_kind, bad_purpose):
        assert resp.status_code == 422, resp.text


async def test_removing_the_app_member_stops_fetches(app, client, admin):
    created = await create_app(client, admin)
    safe_id = await provider_safe(client, admin)
    member = await grant_fetch(client, admin, safe_id, created)
    target = await device(client, admin)
    await account(client, admin, target, safe_id)
    async with caller(app, created.ip) as c:
        headers = await token(c, created)
        assert (await fetch(c, headers, external_ref=target["external_ref"])).status_code == 200
        await client.delete(f"/safes/{safe_id}/members/{member['id']}", headers=admin)
        resp = await fetch(c, headers, external_ref=target["external_ref"])
        assert code(resp) == "credential_not_found"
