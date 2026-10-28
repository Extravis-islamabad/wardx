"""The token route and the app gate (CREDENTIAL_PROVIDER.md §2, §10 "token")."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

import pytest

from src.core.config import get_settings
from tests.integration.provider.provider_support import (
    caller,
    code,
    create_app,
    fetch,
    fetchable,
    new_ip,
    token,
)
from tests.integration.rotation.rotation_support import sql
from tests.integration.safes_support import tag

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_good_secret_gets_a_five_minute_app_token(app, client, admin):
    created = await create_app(client, admin)
    async with caller(app, created.ip) as c:
        resp = await c.post("/provider/token", json=created.creds())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["token_type"] == "Bearer" and data["expires_in"] == 300
    assert resp.headers["cache-control"] == "no-store"
    rows = await sql(
        "SELECT outcome, details::text AS d FROM audit.events WHERE action = 'app.token' "
        "AND object_id = :a",
        a=created.id,
    )
    assert [r["outcome"] for r in rows] == ["success"]
    assert created.secret not in rows[0]["d"] and data["access_token"] not in rows[0]["d"]


async def test_http_basic_works_too(app, client, admin):
    created = await create_app(client, admin)
    basic = base64.b64encode(f"{created.client_id}:{created.secret}".encode()).decode()
    async with caller(app, created.ip) as c:
        resp = await c.post("/provider/token", headers={"Authorization": f"Basic {basic}"})
    assert resp.status_code == 200, resp.text


async def test_bad_secret_unknown_client_and_disabled_app_are_invalid_client(app, client, admin):
    created = await create_app(client, admin)
    async with caller(app, created.ip) as c:
        bad = await c.post("/provider/token", json=created.creds("wxs_wrong-" + tag()))
        unknown = await c.post(
            "/provider/token", json={"client_id": "wxa_nope", "client_secret": "x" * 20}
        )
        await client.patch(f"/apps/{created.id}", headers=admin, json={"enabled": False})
        disabled = await c.post("/provider/token", json=created.creds())
    for resp in (bad, unknown, disabled):
        assert resp.status_code == 401 and code(resp) == "invalid_client", resp.text
    rows = await sql(
        "SELECT outcome, details->>'reason' AS reason FROM audit.events "
        "WHERE action = 'app.token' AND object_id = :a ORDER BY seq",
        a=created.id,
    )
    assert [(r["outcome"], r["reason"]) for r in rows] == [
        ("failure", "bad_secret"),
        ("failure", "disabled"),
    ]


async def test_ip_not_in_allowlist_is_refused(app, client, admin):
    created = await create_app(client, admin)
    async with caller(app, new_ip()) as c:
        resp = await c.post("/provider/token", json=created.creds())
    assert resp.status_code == 403 and code(resp) == "ip_not_allowed"


async def test_empty_allowlist_means_no_access(app, client, admin):
    created = await create_app(client, admin, ip_allowlist=[])
    async with caller(app, created.ip) as c:
        resp = await c.post("/provider/token", json=created.creds())
    assert resp.status_code == 403 and code(resp) == "ip_not_allowed"


async def test_both_secrets_work_during_the_overlap_and_revoked_ones_stop(app, client, admin):
    created = await create_app(client, admin)
    second = (await client.post(f"/apps/{created.id}/secrets", headers=admin, json={})).json()
    new_secret = second["data"]["client_secret"]
    async with caller(app, created.ip) as c:
        old_token = await token(c, created)
        await token(c, created, new_secret)
        first_id = [s for s in second["data"]["app"]["secrets"] if s["slot"] == 1][0]["id"]
        await client.post(f"/apps/{created.id}/secrets/{first_id}/revoke", headers=admin)
        refused = await c.post("/provider/token", json=created.creds())
        assert refused.status_code == 401 and code(refused) == "invalid_client"
        # Tokens issued for the revoked secret die with it.
        resp = await fetch(c, old_token, external_ref="none")
        assert resp.status_code == 401 and code(resp) == "invalid_token"
        await token(c, created, new_secret)


async def test_expired_secret_is_refused(app, client, admin):
    soon = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    created = await create_app(client, admin, secret_expires_at=soon)
    await sql(
        "UPDATE iam.app_secrets SET expires_at = NOW() - INTERVAL '1 second' WHERE app_id = :a",
        a=created.id,
    )
    async with caller(app, created.ip) as c:
        resp = await c.post("/provider/token", json=created.creds())
    assert resp.status_code == 401 and code(resp) == "invalid_client"


async def test_failed_attempts_are_rate_limited_per_client_id(app, client, admin):
    limit = get_settings().provider_token_failures_per_minute
    created = await create_app(client, admin)
    for i in range(limit):
        # Every attempt from another address: only the client_id bucket fills.
        async with caller(app, new_ip()) as c:
            resp = await c.post("/provider/token", json=created.creds(f"wxs_wrong-{i}"))
            assert resp.status_code in (401, 403), resp.text
    async with caller(app, created.ip) as c:
        limited = await c.post("/provider/token", json=created.creds())
    assert limited.status_code == 429 and code(limited) == "rate_limited"
    assert int(limited.headers["retry-after"]) >= 1


async def test_failed_attempts_are_rate_limited_per_source_ip(app, client, admin):
    limit = get_settings().provider_token_failures_per_minute
    created = await create_app(client, admin)
    async with caller(app, created.ip) as c:
        for i in range(limit):
            await c.post("/provider/token", json={"client_id": f"wxa_x{i}", "client_secret": "y"})
        limited = await c.post("/provider/token", json=created.creds())
    assert limited.status_code == 429 and code(limited) == "rate_limited"


async def test_app_tokens_are_refused_on_user_routes(app, client, admin):
    created = await create_app(client, admin)
    async with caller(app, created.ip) as c:
        headers = await token(c, created)
        for path in ("/auth/me", "/accounts", "/targets", "/apps"):
            resp = await c.get(path, headers=headers)
            assert resp.status_code == 401 and code(resp) == "unauthorized", path


async def test_user_tokens_are_refused_on_provider_routes(app, client, admin):
    created = await create_app(client, admin)
    _, target, account = await fetchable(client, admin, created)
    async with caller(app, created.ip) as c:
        resp = await fetch(c, admin, external_ref=target["external_ref"])
        assert resp.status_code == 401 and code(resp) == "invalid_token"
        resp = await c.post(
            f"/provider/credentials/{account['id']}/fetch", headers=admin, json={"purpose": "poll"}
        )
        assert resp.status_code == 401 and code(resp) == "invalid_token"
        missing = await fetch(c, {}, external_ref=target["external_ref"])
        assert missing.status_code == 401 and code(missing) == "invalid_token"


async def test_disabling_an_app_kills_its_tokens_at_once(app, client, admin):
    created = await create_app(client, admin)
    _, target, _ = await fetchable(client, admin, created)
    async with caller(app, created.ip) as c:
        headers = await token(c, created)
        assert (await fetch(c, headers, external_ref=target["external_ref"])).status_code == 200
        await client.patch(f"/apps/{created.id}", headers=admin, json={"enabled": False})
        await client.patch(f"/apps/{created.id}", headers=admin, json={"enabled": True})
        # Re-enabled, the old token stays dead (token_version moved on).
        resp = await fetch(c, headers, external_ref=target["external_ref"])
        assert resp.status_code == 401 and code(resp) == "invalid_token"


async def test_allowlist_is_checked_on_every_fetch(app, client, admin):
    created = await create_app(client, admin)
    _, target, _ = await fetchable(client, admin, created)
    async with caller(app, created.ip) as c:
        headers = await token(c, created)
    async with caller(app, new_ip()) as other:
        resp = await fetch(other, headers, external_ref=target["external_ref"])
    assert resp.status_code == 403 and code(resp) == "ip_not_allowed"


async def test_forwarded_for_is_believed_only_from_trusted_proxies(app, client, admin):
    created = await create_app(client, admin)
    proxy = new_ip()
    xff = {"X-Forwarded-For": f"203.0.113.50, {created.ip}"}
    settings = get_settings()
    async with caller(app, proxy) as c:
        untrusted = await c.post("/provider/token", json=created.creds(), headers=xff)
        assert untrusted.status_code == 403 and code(untrusted) == "ip_not_allowed"
        settings.trusted_proxies = [f"{proxy}/32"]
        try:
            trusted = await c.post("/provider/token", json=created.creds(), headers=xff)
            assert trusted.status_code == 200, trusted.text
            # A forged left-most entry is never what counts.
            forged = {"X-Forwarded-For": f"{created.ip}, 203.0.113.50"}
            resp = await c.post("/provider/token", json=created.creds(), headers=forged)
            assert resp.status_code == 403 and code(resp) == "ip_not_allowed"
        finally:
            settings.trusted_proxies = []
