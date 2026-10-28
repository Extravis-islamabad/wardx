"""Shared setup for the credential provider tests (docs/phase1/CREDENTIAL_PROVIDER.md §10).

Every test talks to the real API over HTTP (ASGI) with the real database. Callers get
their own source address (``AppCaller``), so per-IP failed-attempt counters of one test
never spill into another.
"""

from __future__ import annotations

import random
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from httpx import ASGITransport, AsyncClient

from tests.integration.rotation.rotation_support import sql
from tests.integration.safes_support import tag

DEVICE_PASSWORD = "Prov-Device-Passw0rd-1"  # gitleaks:allow


def new_ip() -> str:
    """A fresh RFC 1918 address for one test's caller."""
    return f"10.{random.randint(64, 250)}.{random.randint(0, 255)}.{random.randint(1, 254)}"  # noqa: S311


@asynccontextmanager
async def caller(app, ip: str):
    """An HTTP client whose connections come from ``ip``."""
    transport = ASGITransport(app=app, client=(ip, 40000))
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


@dataclass
class AppCaller:
    """An application identity, its first secret, and a client calling from an allowed IP."""

    id: str
    client_id: str
    secret: str = field(repr=False)
    ip: str
    body: dict

    def creds(self, secret: str | None = None) -> dict:
        return {"client_id": self.client_id, "client_secret": secret or self.secret}


async def create_app(client, admin, *, ip: str | None = None, **extra) -> AppCaller:
    ip = ip or new_ip()
    body = {"name": f"monetx-{tag()}", "ip_allowlist": [f"{ip}/32"], **extra}
    resp = await client.post("/apps", headers=admin, json=body)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    return AppCaller(
        id=data["app"]["id"],
        client_id=data["client_id"],
        secret=data["client_secret"],
        ip=ip,
        body=data,
    )


async def token(c: AsyncClient, app: AppCaller, secret: str | None = None) -> dict:
    resp = await c.post("/provider/token", json=app.creds(secret))
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def fetch(c: AsyncClient, headers: dict, *, kind: str = "ssh", purpose: str = "poll", **q):
    """POST /provider/credentials/fetch; ``q`` holds the target key and optional username."""
    username = q.pop("username", None)
    body = {"target": q, "kind": kind, "purpose": purpose}
    if username is not None:
        body["username"] = username
    return await c.post("/provider/credentials/fetch", headers=headers, json=body)


def code(resp) -> str:
    return resp.json()["error"]["code"]


async def provider_safe(client, admin, **settings) -> str:
    """A new safe the admin role manages accounts in (seeded directly: no self-grant)."""
    resp = await client.post("/safes", headers=admin, json={"name": f"prov-{tag()}"})
    assert resp.status_code == 201, resp.text
    safe_id = resp.json()["data"]["id"]
    await sql(
        "INSERT INTO inventory.safe_members (safe_id, principal_type, principal_key, "
        "permissions) VALUES (:s, 'role', 'admin', "
        "ARRAY['list','use','retrieve','manage_accounts','view_audit'])",
        s=safe_id,
    )
    if settings:
        resp = await client.put(f"/safes/{safe_id}/app-fetch", headers=admin, json=settings)
        assert resp.status_code == 200, resp.text
    return safe_id


async def grant_fetch(client, admin, safe_id: str, app: AppCaller) -> dict:
    resp = await client.post(
        f"/safes/{safe_id}/members",
        headers=admin,
        json={"principal_type": "app", "principal_key": app.id, "permissions": ["fetch"]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def device(client, admin, *, external_ref: str | None = None, **extra) -> dict:
    """A target standing for a MonetX device (external_ref = MonetX's device id)."""
    resp = await client.post(
        "/targets",
        headers=admin,
        json={
            "name": f"dev-{tag()}",
            "address": f"192.0.2.{random.randint(1, 254)}",  # noqa: S311
            "platform": "cisco_ios",
            "protocol": "ssh",
            "external_ref": external_ref or f"monetx-device-{tag()}",
            **extra,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def account(client, admin, target: dict, safe_id: str, **body) -> dict:
    payload = {"target_id": target["id"], "safe_id": safe_id, "username": "netadmin", **body}
    if "secret" not in body and "snmp" not in body:
        payload["secret"] = DEVICE_PASSWORD
    resp = await client.post("/accounts", headers=admin, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def fetchable(client, admin, app: AppCaller, **settings) -> tuple[str, dict, dict]:
    """(safe id, target, account): a password account the app may fetch."""
    safe_id = await provider_safe(client, admin, **settings)
    await grant_fetch(client, admin, safe_id, app)
    target = await device(client, admin)
    return safe_id, target, await account(client, admin, target, safe_id)
