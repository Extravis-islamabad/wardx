"""HA lab fixtures (opt-in: WARDX_LAB=ha). Brings lab/ha up fresh, starts the six WardX
nodes, seeds a user, a Linux lab target and accounts, and tears everything down after.

The gate is checked before anything is started or probed (tests/lab_gate.py).
"""

from __future__ import annotations

import asyncio
import secrets
import shutil
import subprocess  # noqa: S404 - lab only
import time

import asyncpg
import httpx
import pytest

from tests.lab_gate import lab_skip_reason
from tests.lab_ha import ha_cluster as hc

# The opt-in gate first: without WARDX_LAB=ha nothing is started, probed or contacted.
SKIP_REASON = lab_skip_reason("ha")
if SKIP_REASON is None and shutil.which("docker") is None:
    SKIP_REASON = "Docker CLI not found: HA lab tests skipped"
requires_ha_lab = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")

APIS = {"api-1": 18010, "api-2": 18011}
GATEWAYS = {"gw-a": 12222, "gw-b": 12223}


def docker(*args: str) -> str:
    out = subprocess.run(  # noqa: S603 - fixed docker argv on wardx-lab-ha-* names only
        ["docker", *args],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"docker {args[0]} failed: {out.stderr.strip()[:300]}")
    return out.stdout


async def db() -> asyncpg.Connection:
    """Whichever lab database is the read-write primary."""
    return await asyncpg.connect(
        host=["127.0.0.1", "127.0.0.1"],
        port=list(hc.PG_PORTS),
        user="wardx",
        password=hc.secret("pg-password"),
        database="wardx",
        target_session_attrs="read-write",
        timeout=5,
    )


async def fetchval(sql: str, *args):
    conn = await db()
    try:
        return await conn.fetchval(sql, *args)
    finally:
        await conn.close()


async def fetch(sql: str, *args):
    conn = await db()
    try:
        return await conn.fetch(sql, *args)
    finally:
        await conn.close()


async def wait_for(check, limit: float = 60, every: float = 0.5, what: str = "condition"):
    deadline = time.monotonic() + limit
    last = None
    while time.monotonic() < deadline:
        try:
            last = await check()
            if last:
                return last
        except Exception as exc:  # noqa: BLE001 - lab polling across failovers
            last = exc
        await asyncio.sleep(every)
    raise AssertionError(f"timed out waiting for {what} (last: {last!r})")


def api(name: str, token: str | None = None) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{APIS[name]}/api/v1", headers=headers, timeout=10
    )


async def login(name: str, username: str, password: str) -> str:
    async with api(name) as c:
        resp = await c.post("/auth/login", json={"username": username, "password": password})
        assert resp.status_code == 200, resp.text
        return resp.json()["data"]["access_token"]


async def holds(value):
    """For wait_for on a plain expression evaluated by a lambda."""
    return value


async def api_ready(name: str) -> bool:
    async with api(name) as c:
        return (await c.get("/health/ready")).status_code == 200


@pytest.fixture(scope="module")
async def cluster():
    hc.stop_all()
    hc.lab("down")
    hc.lab("up")
    hc.start("api-1")  # runs the migrations and creates the admin first
    await wait_for(lambda: api_ready("api-1"), 120, what="api-1")
    for name in hc.NODES:
        if name != "api-1":
            hc.start(name)
    await wait_for(lambda: api_ready("api-2"), 120, what="api-2")
    await wait_for(
        lambda: fetchval("SELECT count(*) = 2 FROM ha.gateway_nodes WHERE stopped_at IS NULL"),
        60,
        what="both gateways",
    )
    await wait_for(
        lambda: fetchval("SELECT node FROM ha.scheduler_leader"), 60, what="a scheduler leader"
    )
    yield hc
    hc.stop_all()
    hc.lab("down")


@pytest.fixture(scope="module")
async def seeded(cluster):
    """Admin token, a gateway user, a pinned Linux lab target, its accounts, a dummy target."""
    token = await login("api-1", "admin", hc.secret("admin-password"))
    user_pw = hc.secret("user-password")
    target_pw = hc.secret("target-password")
    async with api("api-1", token) as c:
        resp = await c.post(
            "/users", json={"username": "netops-ha", "password": user_pw, "role": "user"}
        )
        assert resp.status_code == 201, resp.text
        resp = await c.post(
            "/targets",
            json={
                "name": "linux-ha",
                "address": "127.0.0.1",
                "port": hc.TARGET_PORT,
                "platform": "linux",
                "protocol": "ssh",
                "rotation_allowed": True,
            },
        )
        assert resp.status_code == 201, resp.text
        target = resp.json()["data"]

        async def probe():
            r = await c.post(f"/targets/{target['id']}/host-key/probe")
            return r.json()["data"] if r.status_code == 200 else None

        presented = (await wait_for(probe, 60, 1, "the lab target's SSH"))["presented_fingerprint"]
        resp = await c.post(
            f"/targets/{target['id']}/host-key/accept", json={"fingerprint": presented}
        )
        assert resp.status_code == 200, resp.text
        accounts = {}
        for user in ("wardx_rot_sess", "wardx_rot_ha"):
            resp = await c.post(
                "/accounts",
                json={"target_id": target["id"], "username": user, "secret": target_pw},
            )
            assert resp.status_code == 201, resp.text
            accounts[user] = resp.json()["data"]
        resp = await c.post(
            "/targets",
            json={
                "name": "ha-dummy",
                "address": "192.0.2.50",
                "platform": "linux",
                "protocol": "ssh",
            },
        )
        assert resp.status_code == 201, resp.text
        dummy = resp.json()["data"]
    # New accounts get a first scheduled verify; let it finish (a running job blocks access).
    await asyncio.sleep(6)
    await wait_for(
        lambda: fetchval(
            "SELECT count(*) = 0 FROM access.rotation_jobs WHERE target_id = $1::uuid "
            "AND status IN ('pending', 'running', 'waiting_release')",
            target["id"],
        ),
        90,
        1,
        "the first verifies",
    )
    return {
        "token": token,
        "user_password": user_pw,
        "target": target,
        "accounts": accounts,
        "dummy": dummy,
        "nonce": secrets.token_hex(4),
    }
