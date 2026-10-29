"""HA lab failover scenarios (HA_DR.md §8, §10). Opt-in: WARDX_LAB=ha.

Run in file order; each scenario leaves the cluster usable for the next:
wrong KEK -> API node killed -> scheduler leader killed -> gateway killed -> primary killed.
"""

from __future__ import annotations

import asyncio
import signal

import asyncssh
import pytest
from minio import Minio

from tests.lab_ha import ha_cluster as hc
from tests.lab_ha.conftest import (
    GATEWAYS,
    api,
    api_ready,
    db,
    docker,
    fetch,
    fetchval,
    holds,
    requires_ha_lab,
    wait_for,
)

pytestmark = [requires_ha_lab, pytest.mark.asyncio(loop_scope="session")]


async def test_node_with_the_wrong_kek_refuses_to_start(cluster, seeded):
    wrong = hc.Node("api-wrongkek", "api_only", 18012)
    proc = hc.start(wrong.name, node=wrong, kek_file="kek-wrong")
    code = await asyncio.wait_for(asyncio.to_thread(proc.wait), 60)
    assert code != 0
    assert "KEK canary check failed" in hc.log_of(wrong.name)
    assert not await fetchval("SELECT count(*) FROM ha.gateway_nodes WHERE node = $1", wrong.name)


async def test_api_node_killed_the_other_serves(cluster, seeded):
    hc.signal_node("api-1", signal.SIGKILL)
    assert await api_ready("api-2")
    async with api("api-2", seeded["token"]) as c:  # a token from api-1 works on api-2
        assert (await c.get("/sessions")).status_code == 200
    hc.start("api-1")
    await wait_for(lambda: api_ready("api-1"), 60, what="api-1 back")


async def test_scheduler_leader_killed_standby_takes_over(cluster, seeded):
    leader, term = (await fetch("SELECT node, term FROM ha.scheduler_leader"))[0]
    hc.signal_node(leader, signal.SIGKILL)

    async def new_leader():
        row = (await fetch("SELECT node, term FROM ha.scheduler_leader"))[0]
        return row if row["node"] != leader and row["term"] > term else None

    row = await wait_for(new_leader, 45, what="a new scheduler leader")
    elected = await fetchval(
        "SELECT count(*) FROM audit.events WHERE action = 'scheduler.leader_elected' "
        "AND details->>'node' = $1 AND details->>'previous' = $2",
        row["node"],
        leader,
    )
    assert elected == 1
    async with api("api-2", seeded["token"]) as c:
        data = (await c.get("/health/cluster")).json()["data"]
    assert data["leader"]["node"] == row["node"] and data["leader"]["fresh"] is True
    hc.start(leader)  # back as a standby


async def _gateway_session(port: int, seeded):
    return await asyncssh.connect(
        "127.0.0.1",
        port,
        username="netops-ha%wardx_rot_sess%linux-ha",
        password=seeded["user_password"],
        known_hosts=None,
        client_keys=None,
        agent_path=None,
        config=None,
        preferred_auth="password",
    )


async def _read_until(stream, needle: str, limit: float = 15) -> str:
    buf = ""
    async with asyncio.timeout(limit):
        while needle not in buf:
            chunk = await stream.read(4096)
            if not chunk:
                break
            buf += chunk
    return buf


async def test_killed_gateway(cluster, seeded):
    marker = f"ha-marker-{seeded['nonce']}"
    conn = await _gateway_session(GATEWAYS["gw-a"], seeded)
    key_a = conn.get_server_host_key().get_fingerprint("sha256")
    proc = await conn.create_process(term_type="xterm", term_size=(100, 30))
    greeting = await _read_until(proc.stdout, "$")
    if "$" not in greeting:
        err = await asyncio.wait_for(proc.stderr.read(4096), 5)
        raise AssertionError(f"no shell prompt: {greeting!r} {err!r}")
    proc.stdin.write(f"echo {marker}\n")
    await _read_until(proc.stdout, f"{marker}\r\n")
    sid, checkout_id = (
        await fetch(
            "SELECT id, checkout_id FROM access.sessions WHERE gateway_node = 'gw-a' "
            "AND status = 'active' ORDER BY started_at DESC LIMIT 1"
        )
    )[0]
    await asyncio.sleep(3)  # the flush interval seals and uploads the output so far

    hc.signal_node("gw-a", signal.SIGKILL)  # the node dies with the live session

    async def ended():
        row = await fetch(
            "SELECT status, close_reason, recording_encrypted, recording_incomplete, "
            "recording_key, recording_sha256 FROM access.sessions WHERE id = $1",
            sid,
        )
        return row[0] if row[0]["status"] != "active" else None

    row = await wait_for(ended, 60, 1, "the lost-node sweep")
    conn.close()
    assert row["status"] == "terminated" and row["close_reason"] == "Gateway node lost"
    assert row["recording_encrypted"] and row["recording_incomplete"]
    assert row["recording_sha256"] is None
    assert (
        await fetchval("SELECT status FROM access.checkouts WHERE id = $1", checkout_id)
        == "returned"
    )
    safe = await fetchval(
        "SELECT safe_id FROM audit.events WHERE action = 'session.end' AND object_id = $1", sid
    )
    assert safe is not None

    # The partial recording is in MinIO, ciphertext only, and replays from another node.
    minio = Minio(
        f"127.0.0.1:{hc.MINIO_PORT}",
        access_key="wardx-lab",
        secret_key=hc.secret("minio-password"),
        secure=False,
    )
    obj = minio.get_object(hc.BUCKET, row["recording_key"])
    stored = obj.read()
    obj.close()
    obj.release_conn()
    assert marker.encode() not in stored and stored.startswith(b"WXREC")
    async with api("api-2", seeded["token"]) as c:
        rec = await c.get(f"/sessions/{sid}/recording")
    assert rec.status_code == 200, rec.text
    assert rec.headers["x-wardx-recording-incomplete"] == "true"
    assert marker in rec.text

    # Reconnect through gateway B: the same host key, and it works.
    conn = await _gateway_session(GATEWAYS["gw-b"], seeded)
    try:
        assert conn.get_server_host_key().get_fingerprint("sha256") == key_a
        result = await conn.run("echo via-b", timeout=20)
        assert result.exit_status == 0 and "via-b" in result.stdout
    finally:
        conn.close()
    hc.start("gw-a")


async def test_killed_primary(cluster, seeded):
    token = seeded["token"]
    async with api("api-2", token) as c:
        assert (await c.get("/health/cluster")).json()["data"]["replication"]["sync_state"] == (
            "sync"
        )
    rot = seeded["accounts"]["wardx_rot_ha"]
    version_before = await fetchval(
        "SELECT secret_version FROM inventory.accounts WHERE id = $1::uuid", rot["id"]
    )
    term_before = await fetchval("SELECT term FROM ha.scheduler_leader")

    # Writes keep going against both API nodes the whole time.
    acked: list[tuple[str, str, str]] = []
    stop = asyncio.Event()

    async def writer():
        i = 0
        clients = [api("api-1", token), api("api-2", token)]
        try:
            while not stop.is_set():
                i += 1
                name = f"wardx_rot_w{seeded['nonce']}_{i}"
                value = f"Ha-Secret-{seeded['nonce']}-{i}"
                try:
                    resp = await clients[i % 2].post(
                        "/accounts",
                        json={
                            "target_id": seeded["dummy"]["id"],
                            "username": name,
                            "secret": value,
                        },
                    )
                    if resp.status_code == 201:
                        acked.append((resp.json()["data"]["id"], name, value))
                except Exception:  # noqa: BLE001,S110 - failover window: expected errors
                    pass
                await asyncio.sleep(0.05)
        finally:
            for c in clients:
                await c.aclose()

    writing = asyncio.create_task(writer())
    await wait_for(lambda: holds(len(acked) >= 10), 30, 0.2, "first writes")

    # An on-demand rotation; the primary dies while it is in flight.
    async with api("api-1", token) as c:
        resp = await c.post(f"/accounts/{rot['id']}/rotate", json={"reason": "HA lab failover"})
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["data"]["id"]
    conn = await db()
    try:
        async with asyncio.timeout(60):
            while True:
                status = await conn.fetchval(
                    "SELECT status FROM access.rotation_jobs WHERE id = $1::uuid", job_id
                )
                if status in ("candidate_stored", "device_changed", "persisted", "succeeded"):
                    break
                await asyncio.sleep(0.01)
    finally:
        await conn.close()
    in_flight_at_kill = status
    docker("kill", "wardx-lab-ha-pg1")
    acked_before_kill = len(acked)
    await asyncio.sleep(2)
    hc.lab("promote")

    # The app follows the promotion (multi-host URL, target_session_attrs=read-write).
    await wait_for(
        lambda: holds(len(acked) >= acked_before_kill + 10),
        90,
        0.5,
        "writes after promotion",
    )
    stop.set()
    await writing

    # No acknowledged secret or audit event lost; secrets still decrypt.
    ids = [a for a, _, _ in acked]
    found = await fetchval(
        "SELECT count(*) FROM inventory.accounts a JOIN vault.secrets s "
        "ON s.owner_id = a.id AND s.version = a.secret_version WHERE a.id = ANY($1::uuid[])",
        ids,
    )
    assert found == len(ids)
    audited = await fetchval(
        "SELECT count(DISTINCT object_id) FROM audit.events WHERE action = 'account.create' "
        "AND object_id = ANY($1::uuid[])",
        ids,
    )
    assert audited == len(ids)
    async with api("api-2", token) as c:
        for account_id, _, value in (acked[0], acked[acked_before_kill - 1], acked[-1]):
            co = await c.post("/checkouts", json={"account_id": account_id, "reason": "HA check"})
            assert co.status_code == 201, co.text
            co_id = co.json()["data"]["id"]
            shown = await c.post(f"/checkouts/{co_id}/reveal")
            assert shown.json()["data"]["value"] == value
            await c.post(f"/checkouts/{co_id}/checkin")
        chain = (await c.post("/audit/verify")).json()["data"]
    assert chain["ok"] is True, chain

    # Scheduler leadership is re-established on the new primary.
    await wait_for(
        lambda: fetchval(
            "SELECT term > $1 AND last_seen > now() - interval '15 seconds' "
            "FROM ha.scheduler_leader",
            term_before,
        ),
        60,
        1,
        "leadership on the new primary",
    )

    # The rotation in flight completes, once.
    async def job_done():
        s = await fetchval("SELECT status FROM access.rotation_jobs WHERE id = $1::uuid", job_id)
        return (
            s
            if s not in ("pending", "running", "candidate_stored", "device_changed", "persisted")
            else None
        )

    final = await wait_for(job_done, 120, 1, "the in-flight rotation")
    assert final == "succeeded", (final, in_flight_at_kill)
    assert (
        await fetchval(
            "SELECT secret_version FROM inventory.accounts WHERE id = $1::uuid", rot["id"]
        )
        == version_before + 1
    )
    assert (
        await fetchval(
            "SELECT count(*) FROM vault.secrets WHERE owner_id = $1::uuid AND version > $2",
            rot["id"],
            version_before,
        )
        == 1
    )
    assert (
        await fetchval(
            "SELECT count(*) FROM audit.events WHERE action = 'rotation.succeeded' "
            "AND object_id = $1::uuid",
            job_id,
        )
        == 1
    )
    assert (
        await fetchval(
            "SELECT count(*) FROM access.rotation_jobs WHERE account_id = $1::uuid "
            "AND reason <> 'verify'",
            rot["id"],
        )
        == 1
    )
    # The device holds the vault's current password: a verify succeeds.
    async with api("api-2", token) as c:
        resp = await c.post(f"/accounts/{rot['id']}/verify", json={"reason": "after failover"})
        assert resp.status_code == 202, resp.text
        verify_id = resp.json()["data"]["id"]

    async def verified():
        s = await fetchval("SELECT status FROM access.rotation_jobs WHERE id = $1::uuid", verify_id)
        return s if s not in ("pending", "running") else None

    assert await wait_for(verified, 60, 1, "the verify") == "succeeded"

    # The promoted primary runs without a synchronous standby: the degraded alert is up.
    async def degraded_alert():
        async with api("api-2", token) as c:
            items = (
                await c.get("/alerts", params={"acknowledged": "false", "page_size": 50})
            ).json()["data"]
        return any(a["kind"] == "cluster.sync_degraded" for a in items)

    assert await wait_for(degraded_alert, 30, 1, "the degraded-sync alert")
    print(f"HA lab: {len(acked)} writes acknowledged, rotation caught at {in_flight_at_kill}")
