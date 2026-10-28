"""End-to-end: inventory, vault, approvals, check-out, audit chain — through the HTTP API."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text

from src.core.db import session_factory
from src.core.enums import DEFAULT_APPROVAL_SAFE_ID
from src.dependencies.access import build_checkout_service

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _target(client, admin, name: str) -> str:
    resp = await client.post(
        "/targets",
        headers=admin,
        json={
            "name": name,
            "address": "10.0.0.1",
            "platform": "mikrotik_routeros",
            "protocol": "ssh",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["port"] == 22
    return resp.json()["data"]["id"]


async def _account(
    client, admin, target_id: str, username: str, secret: str | None, **policy
) -> str:
    body = {"target_id": target_id, "username": username, **policy}
    if secret:
        body["secret"] = secret
    resp = await client.post("/accounts", headers=admin, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def test_direct_checkout_reveal_and_exclusivity(client, admin, make_user):
    alice, bob = await make_user("alice1"), await make_user("bob1")
    tid = await _target(client, admin, "edge-rtr-1")
    aid = await _account(client, admin, tid, "admin", "Rtr-Secret-1")

    resp = await client.post("/checkouts", headers=alice, json={"account_id": aid})
    assert resp.status_code == 409  # a reason is required

    resp = await client.post(
        "/checkouts",
        headers=alice,
        json={"account_id": aid, "reason": "fix BGP", "duration_minutes": 30},
    )
    assert resp.status_code == 201, resp.text
    co = resp.json()["data"]

    reveal = await client.post(f"/checkouts/{co['id']}/reveal", headers=alice)
    assert reveal.status_code == 200
    assert reveal.json()["data"]["value"] == "Rtr-Secret-1"
    assert reveal.headers["cache-control"] == "no-store"

    # Exclusive: bob is turned away while alice holds it, and cannot reveal her check-out.
    resp = await client.post("/checkouts", headers=bob, json={"account_id": aid, "reason": "audit"})
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["held_by"] == "alice1"
    assert (await client.post(f"/checkouts/{co['id']}/reveal", headers=bob)).status_code == 403

    assert (await client.post(f"/checkouts/{co['id']}/checkin", headers=alice)).status_code == 200
    assert (await client.post(f"/checkouts/{co['id']}/reveal", headers=alice)).status_code == 409
    resp = await client.post("/checkouts", headers=bob, json={"account_id": aid, "reason": "audit"})
    assert resp.status_code == 201


async def test_approval_flow_and_dual_control(client, admin, make_user):
    carol = await make_user("carol1")
    approver = await make_user("approver1", role="approver")
    tid = await _target(client, admin, "core-sw-1")
    # Approval is the safe's policy: the migrated "Default (approval required)" safe.
    aid = await _account(
        client, admin, tid, "root", "Core-Secret-1", safe_id=str(DEFAULT_APPROVAL_SAFE_ID)
    )

    # No request: refused. Requesting without approval need: tested below.
    resp = await client.post("/checkouts", headers=carol, json={"account_id": aid, "reason": "x"})
    assert resp.status_code == 403

    resp = await client.post(
        "/requests",
        headers=carol,
        json={"account_id": aid, "reason": "change window CHG-42", "duration_minutes": 45},
    )
    assert resp.status_code == 201, resp.text
    req_id = resp.json()["data"]["id"]

    # A plain user cannot decide; the approver can.
    resp = await client.post(f"/requests/{req_id}/decision", headers=carol, json={"approve": True})
    assert resp.status_code == 403
    resp = await client.post(
        f"/requests/{req_id}/decision", headers=approver, json={"approve": True}
    )
    assert resp.status_code == 200 and resp.json()["data"]["status"] == "approved"

    resp = await client.post(
        "/checkouts", headers=carol, json={"account_id": aid, "request_id": req_id}
    )
    assert resp.status_code == 201, resp.text
    co = resp.json()["data"]
    assert co["reason"] == "change window CHG-42"
    reveal = await client.post(f"/checkouts/{co['id']}/reveal", headers=carol)
    assert reveal.json()["data"]["value"] == "Core-Secret-1"

    # The request is spent.
    resp = await client.get("/requests", headers=carol, params={"mine": True})
    assert resp.json()["data"][0]["status"] == "used"

    # Approvers cannot approve their own requests.
    resp = await client.post(
        "/requests",
        headers=approver,
        json={"account_id": aid, "reason": "self", "duration_minutes": 10},
    )
    own = resp.json()["data"]["id"]
    resp = await client.post(f"/requests/{own}/decision", headers=approver, json={"approve": True})
    assert resp.status_code == 403


async def test_concurrent_checkouts_of_exclusive_account_one_wins(client, admin, make_user):
    users = [await make_user(f"race{i}") for i in range(5)]
    tid = await _target(client, admin, "fw-race")
    aid = await _account(client, admin, tid, "admin", "Race-Secret-1")
    results = await asyncio.gather(
        *[
            client.post("/checkouts", headers=u, json={"account_id": aid, "reason": "race"})
            for u in users
        ]
    )
    codes = sorted(r.status_code for r in results)
    assert codes == [201, 409, 409, 409, 409]


async def test_rbac_and_secret_never_listed(client, admin, make_user):
    dave = await make_user("dave1")
    resp = await client.post(
        "/targets",
        headers=dave,
        json={"name": "nope", "address": "1.1.1.1", "platform": "linux", "protocol": "ssh"},
    )
    assert resp.status_code == 403
    assert (await client.get("/audit/events", headers=dave)).status_code == 403
    assert (await client.get("/users", headers=dave)).status_code == 403

    tid = await _target(client, admin, "srv-list")
    await _account(client, admin, tid, "svc", "Never-Listed-1")
    listing = await client.get("/accounts", headers=dave, params={"search": "srv-list"})
    assert listing.status_code == 200
    assert "Never-Listed-1" not in listing.text
    assert listing.json()["data"][0]["has_secret"] is True

    async with session_factory()() as session:
        blobs = (
            (await session.execute(text("SELECT ciphertext FROM vault.secrets"))).scalars().all()
        )
    assert blobs and all(b"Never-Listed-1" not in bytes(b) for b in blobs)


async def test_expiry_sweep_closes_overdue_checkouts(client, admin, make_user):
    erin = await make_user("erin1")
    tid = await _target(client, admin, "exp-host")
    aid = await _account(client, admin, tid, "root", "Exp-Secret-1")
    co = (
        await client.post("/checkouts", headers=erin, json={"account_id": aid, "reason": "test"})
    ).json()["data"]

    async with session_factory()() as session:
        await session.execute(
            text(
                "UPDATE access.checkouts SET expires_at = NOW() - INTERVAL '1 minute' "
                "WHERE id = :id"
            ),
            {"id": uuid.UUID(co["id"])},
        )
        await session.commit()
        result = await build_checkout_service(session).expire_overdue()
    assert result["checkouts"] >= 1
    resp = await client.get("/checkouts", headers=erin, params={"mine": True})
    assert next(c for c in resp.json()["data"] if c["id"] == co["id"])["status"] == "expired"


async def test_login_lockout(client, make_user):
    await make_user("frank1")
    for _ in range(5):
        resp = await client.post("/auth/login", json={"username": "frank1", "password": "wrong"})
        assert resp.status_code == 401
    resp = await client.post(
        "/auth/login", json={"username": "frank1", "password": "User-Passw0rd-frank1"}
    )
    assert resp.status_code == 423


async def test_logout_revokes_tokens(client, make_user):
    gina = await make_user("gina1")
    assert (await client.get("/auth/me", headers=gina)).status_code == 200
    assert (await client.post("/auth/logout", headers=gina)).status_code == 200
    assert (await client.get("/auth/me", headers=gina)).status_code == 401


async def test_last_admin_cannot_be_demoted(client, admin):
    me = (await client.get("/auth/me", headers=admin)).json()["data"]
    resp = await client.patch(f"/users/{me['id']}", headers=admin, json={"role": "user"})
    assert resp.status_code == 409


async def test_audit_chain_verifies_and_is_append_only(client, admin):
    resp = await client.post("/audit/verify", headers=admin)
    data = resp.json()["data"]
    assert data["ok"] is True and data["checked"] > 10

    events = (
        await client.get("/audit/events", headers=admin, params={"action": "secret.reveal"})
    ).json()
    assert events["total"] >= 2

    async with session_factory()() as session:
        with pytest.raises(Exception, match="append-only"):
            await session.execute(text("UPDATE audit.events SET action = 'x' WHERE seq = 1"))
        await session.rollback()
        with pytest.raises(Exception, match="append-only"):
            await session.execute(text("DELETE FROM audit.events"))
        await session.rollback()

        # Someone bypassing the trigger (superuser) is still caught by the chain.
        original = (
            await session.execute(text("SELECT details::text FROM audit.events WHERE seq = 3"))
        ).scalar_one()

        async def set_details(value: str) -> None:
            await session.execute(
                text("ALTER TABLE audit.events DISABLE TRIGGER trg_audit_no_update")
            )
            await session.execute(
                text("UPDATE audit.events SET details = CAST(:d AS jsonb) WHERE seq = 3"),
                {"d": value},
            )
            await session.execute(
                text("ALTER TABLE audit.events ENABLE TRIGGER trg_audit_no_update")
            )
            await session.commit()

        await set_details('{"forged": true}')
        data = (await client.post("/audit/verify", headers=admin)).json()["data"]
        assert data["ok"] is False and data["broken_at_seq"] == 3

        # Restored, the chain verifies again (and later test files see a clean chain).
        await set_details(original)
    data = (await client.post("/audit/verify", headers=admin)).json()["data"]
    assert data["ok"] is True
