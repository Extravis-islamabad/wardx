"""Guard: every audit event about an account, request, check-out or session records the
safe it happened in (audit.events.safe_id). Runs a representative flow through the API,
the gateway, directory sync and break-glass, then checks the events it wrote.

New event types that are about one of these objects (rotation jobs included, Phase 1 c;
credential provider fetches, Phase 1 d) must set or resolve a safe, or this test fails.
Lives under tests/security so it runs after the integration suite: it disables a
directory user via sync.
"""

from __future__ import annotations

import asyncio

import asyncssh
import ldap3
import pytest
from sqlalchemy import text

from src.core.db import session_factory
from src.services.directory import directory_service
from tests.conftest import DEVICE_USER
from tests.integration.approvals_support import (
    APPROVER_PERMS,
    REQUESTER_PERMS,
    approval_safe,
    decide,
    person,
    request_access,
)
from tests.integration.safes_support import (
    ALL_PERMS,
    checkout,
    grant,
    me,
    new_account,
    new_safe,
    tag,
)
from tests.integration.test_break_glass import REASON, make_holder
from tests.integration.test_directory import CONFIG
from tests.ldap_mock import BASE, OPERATORS, SVC_DN, SVC_PW, build_directory, mock_factory

pytestmark = pytest.mark.asyncio(loop_scope="session")

SAFE_OBJECTS = ("account", "request", "checkout", "session", "rotation_job")


async def _scalar(sql: str, **params):
    async with session_factory()() as s:
        return (await s.execute(text(sql), params)).scalar()


async def _gateway_session(gateway) -> None:
    conn = await asyncssh.connect(
        "127.0.0.1",
        gateway.port,
        username=f"netops1%{DEVICE_USER}%fake-rtr",
        password="User-Passw0rd-netops1",
        known_hosts=None,
        client_keys=None,
        agent_path=None,
        config=None,
        preferred_auth="password",
    )
    blocked = await conn.run("write erase", timeout=5)
    assert blocked.exit_status == 126
    conn.close()
    for _ in range(50):
        status = await _scalar(
            "SELECT s.status FROM access.sessions s JOIN iam.users u ON u.id = s.user_id "
            "WHERE u.username = 'netops1' ORDER BY started_at DESC LIMIT 1"
        )
        if status != "active":
            return
        await asyncio.sleep(0.1)
    raise AssertionError("gateway session did not close")


async def _directory_sync_revoke(client, admin) -> None:
    server = build_directory()
    dn = f"cn=Guard User,ou=people,{BASE}"
    svc = ldap3.Connection(server, user=SVC_DN, password=SVC_PW, client_strategy=ldap3.MOCK_SYNC)
    svc.bind()
    svc.strategy.add_entry(
        dn,
        {
            "objectClass": ["user"],
            "sAMAccountName": "guarduser",
            "userPassword": "Dir-Pass-guard1",  # gitleaks:allow
            "displayName": "Guard User",
            "memberOf": [OPERATORS],
        },
    )
    directory_service.set_connection_factory(mock_factory(server))
    await client.put("/directory", headers=admin, json={**CONFIG, "sync_interval_minutes": 0})
    try:
        login = await client.post(
            "/auth/login", json={"username": "guarduser", "password": "Dir-Pass-guard1"}
        )
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
        # A Default-safe account (role 'user' holds retrieve there), checked out by them.
        target = (
            await client.post(
                "/targets",
                headers=admin,
                json={
                    "name": f"g-{tag()}",
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
                json={"target_id": target["id"], "username": "svc", "secret": "Guard-Secret-1"},
            )
        ).json()["data"]
        assert (await checkout(client, headers, account["id"])).status_code == 201
        svc.delete(dn)
        resp = await client.post("/directory/sync", headers=admin, json={"force": True})
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["revoked_checkouts"] >= 1
    finally:
        await client.put("/directory", headers=admin, json={**CONFIG, "enabled": False})
        directory_service.set_connection_factory(directory_service.default_connection)


async def _rotation_flow(client, admin) -> None:
    """Rotate, verify (untrustworthy), and a job that needs attention, then resolved."""
    from src.core.config import get_settings
    from src.rotation.drivers.registry import default_registry
    from tests.integration.rotation.fake_driver import FAKE_PLATFORM
    from tests.integration.rotation.rotation_support import CrashAt, Lab

    settings = get_settings()
    settings.rotation_enabled = True
    rot = Lab(client, admin)
    try:
        with default_registry().override(FAKE_PLATFORM, rot.driver):
            account = await rot.account()
            assert (await rot.run((await rot.request(account["id"]))["id"]))["status"] == (
                "succeeded"
            )
            rot.device.accept_any = True
            await rot.run((await rot.request(account["id"], "verify"))["id"])
            rot.device.accept_any = False
            other = await rot.account()

            async def scramble():
                rot.device.passwords[other["username"]] = "Neither-Of-Them-Works-1"

            job = await rot.request(other["id"])
            done = await rot.run(job["id"], CrashAt("persisted", scramble))
            assert done["status"] == "needs_attention"
            resp = await client.post(
                f"/rotation/jobs/{job['id']}/resolve",
                headers=admin,
                json={"action": "keep_current", "note": "checked by hand"},
            )
            assert resp.status_code == 200, resp.text
    finally:
        settings.rotation_enabled = False


async def _provider_fetches(app, client, admin) -> None:
    """An app fetch that is served and one that is refused for the account's state."""
    from tests.integration.provider.provider_support import (
        caller,
        create_app,
        fetch,
        fetchable,
        token,
    )
    from tests.integration.rotation.rotation_support import sql

    created = await create_app(client, admin)
    _, target, account = await fetchable(client, admin, created)
    async with caller(app, created.ip) as c:
        headers = await token(c, created)
        assert (await fetch(c, headers, external_ref=target["external_ref"])).status_code == 200
        await sql(
            "UPDATE inventory.accounts SET sync_status = 'verify_untrustworthy' WHERE id = :a",
            a=account["id"],
        )
        assert (await fetch(c, headers, external_ref=target["external_ref"])).status_code == 409


async def test_every_account_related_event_records_its_safe(
    app, client, admin, make_user, gateway, lab
):
    start = await _scalar("SELECT COALESCE(MAX(seq), 0) FROM audit.events")

    # Check-out, reveal, check-in.
    safe_id = await new_safe(client, admin)
    keeper = await make_user(f"keeper{tag()}", role="admin")
    await grant(client, admin, safe_id, "user", (await me(client, keeper))["id"], ALL_PERMS)
    account = await new_account(client, keeper, safe_id)
    co = (await checkout(client, keeper, account["id"])).json()["data"]
    await client.post(f"/checkouts/{co['id']}/reveal", headers=keeper)
    await client.post(f"/checkouts/{co['id']}/checkin", headers=keeper)

    # Request and decision.
    appr = await approval_safe(client, admin, make_user, levels=[{"required_approvals": 1}])
    requester = await person(client, make_user, admin, appr["safe_id"], REQUESTER_PERMS)
    approver = await person(client, make_user, admin, appr["safe_id"], APPROVER_PERMS)
    req = (await request_access(client, requester["headers"], appr["account"]["id"])).json()
    assert (await decide(client, approver["headers"], req["data"]["id"])).status_code == 200

    # Gateway session: connect, a blocked command, disconnect.
    await _gateway_session(gateway)

    # Directory sync revokes a check-out.
    await _directory_sync_revoke(client, admin)

    # Break-glass.
    holder = await make_holder(client, admin, make_user)
    resp = await client.post(
        f"/accounts/{account['id']}/emergency-reveal",
        headers=holder["headers"],
        json={"reason": REASON},
    )
    assert resp.status_code == 200, resp.text

    # Rotation: request, run, verify, needs attention and its resolution.
    await _rotation_flow(client, admin)

    # Credential provider: a served and a refused app fetch.
    await _provider_fetches(app, client, admin)

    async with session_factory()() as s:
        rows = (
            await s.execute(
                text("SELECT action, object_type, safe_id FROM audit.events WHERE seq > :start"),
                {"start": start},
            )
        ).all()
    actions = {r.action for r in rows}
    for expected in (
        "checkout.create",
        "secret.reveal",
        "checkout.return",
        "request.create",
        "request.approve",
        "session.start",
        "secret.inject",
        "session.command_blocked",
        "session.end",
        "checkout.revoke",
        "secret.emergency_reveal",
        "rotation.request_rotate",
        "rotation.succeeded",
        "rotation.request_verify",
        "rotation.verify",
        "rotation.verify_untrustworthy",
        "rotation.needs_attention",
        "rotation.resolve",
        "secret.app_fetch",
    ):
        assert expected in actions, f"the flow did not produce {expected}"

    missing = sorted(
        {
            (r.action, r.object_type)
            for r in rows
            if r.object_type in SAFE_OBJECTS and r.safe_id is None
        }
    )
    assert missing == [], f"events about account objects without a safe_id: {missing}"
    # Host-key events of a gateway session are tied to its account's safe too.
    host_key = [r for r in rows if r.action.startswith("target.host_key") and r.safe_id is None]
    assert host_key == []
