"""SSH gateway end to end: user -> gateway -> fake device, through the real broker and database."""

from __future__ import annotations

import asyncio
import json

import asyncssh
import pytest
from sqlalchemy import text

from src.core.db import session_factory
from tests.integration.conftest import DEVICE_PASSWORD, DEVICE_USER

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _connect(gateway, login: str, password: str) -> asyncssh.SSHClientConnection:
    return await asyncssh.connect(
        "127.0.0.1",
        gateway.port,
        username=login,
        password=password,
        known_hosts=None,
        client_keys=None,
        agent_path=None,
        config=None,
        preferred_auth="password",
    )


async def _read_until(stream, needle: str, limit: float = 5) -> str:
    buf = ""
    async with asyncio.timeout(limit):
        while needle not in buf:
            chunk = await stream.read(4096)
            if not chunk:
                break
            buf += chunk
    return buf


async def _latest_session(login_user: str) -> dict:
    async with session_factory()() as s:
        row = (
            (
                await s.execute(
                    text(
                        "SELECT s.* FROM access.sessions s JOIN iam.users u ON u.id = s.user_id "
                        "WHERE u.username = :u ORDER BY started_at DESC LIMIT 1"
                    ),
                    {"u": login_user},
                )
            )
            .mappings()
            .one()
        )
    return dict(row)


async def _wait_closed(login_user: str) -> dict:
    for _ in range(50):
        row = await _latest_session(login_user)
        if row["status"] != "active":
            return row
        await asyncio.sleep(0.1)
    raise AssertionError("session did not close")


async def test_shell_session_injects_credential_blocks_and_records(
    gateway, lab, device, client, admin
):
    conn = await _connect(gateway, f"netops1%{DEVICE_USER}%fake-rtr", "User-Passw0rd-netops1")
    proc = await conn.create_process(term_type="xterm", term_size=(100, 30))
    intro = await _read_until(proc.stdout, "fake-rtr# ")
    assert "Session is recorded" in intro and "Command policy applies" in intro

    proc.stdin.write("show version\r")
    assert "FakeOS 1.0" in await _read_until(proc.stdout, "FakeOS")

    proc.stdin.write("reload\r")
    blocked = await _read_until(proc.stdout, "Blocked by policy")
    assert "No reloads or wipes" in blocked

    proc.stdin.write("exit\r")
    await asyncio.wait_for(proc.wait_closed(), 5)
    conn.close()

    # The device got the vaulted password, ran show version, never ran reload.
    assert (DEVICE_USER, DEVICE_PASSWORD) in device.logins
    assert "show version" in device.executed and "reload" not in device.executed

    row = await _wait_closed("netops1")
    assert row["status"] == "closed"
    assert (row["commands_count"], row["blocked_count"]) == (3, 1)
    assert row["checkout_id"] is not None

    sid = str(row["id"])
    cmds = (await client.get(f"/sessions/{sid}/commands", headers=admin)).json()["data"]
    assert [(c["command"], c["verdict"]) for c in cmds] == [
        ("show version", "allowed"),
        ("reload", "blocked"),
        ("exit", "allowed"),
    ]

    rec = await client.get(f"/sessions/{sid}/recording", headers=admin)
    assert rec.status_code == 200
    assert rec.headers["x-wardx-recording-verified"] == "true"
    lines = rec.text.splitlines()
    assert json.loads(lines[0])["version"] == 2
    played = "".join(json.loads(line)[2] for line in lines[1:] if json.loads(line)[1] == "o")
    assert "FakeOS 1.0" in played and DEVICE_PASSWORD not in played

    # The gateway's own check-out was handed back; the host key got pinned.
    co = (await client.get("/checkouts", headers=lab["user_headers"], params={"mine": True})).json()
    assert co["data"][0]["status"] == "returned"
    tgt = (await client.get(f"/targets/{lab['target']['id']}", headers=admin)).json()["data"]
    assert tgt["ssh_host_key_fingerprint"] == device.host_key.get_fingerprint("sha256")


async def test_exec_mode_runs_and_blocks_single_commands(gateway, lab, device):
    conn = await _connect(gateway, f"netops1%{DEVICE_USER}%fake-rtr", "User-Passw0rd-netops1")
    ok = await conn.run("show version", timeout=5)
    assert "FakeOS 1.0" in ok.stdout and ok.exit_status == 0
    denied = await conn.run("write erase", timeout=5)
    assert denied.exit_status == 126 and "Blocked by policy" in denied.stdout
    assert "write erase" not in device.executed
    conn.close()


async def test_wrong_password_and_unknown_target(gateway, lab):
    with pytest.raises(asyncssh.PermissionDenied):
        await _connect(gateway, f"netops1%{DEVICE_USER}%fake-rtr", "wrong")
    conn = await _connect(gateway, "netops1%nope%no-such-box", "User-Passw0rd-netops1")
    result = await conn.run(timeout=5)
    assert result.exit_status == 1 and "No active target named 'no-such-box'" in result.stderr
    conn.close()


async def test_approval_required_account_refused_without_approval(gateway, lab, client, admin):
    await client.patch(
        f"/accounts/{lab['account']['id']}", headers=admin, json={"requires_approval": True}
    )
    try:
        conn = await _connect(gateway, f"netops1%{DEVICE_USER}%fake-rtr", "User-Passw0rd-netops1")
        result = await conn.run("show version", timeout=5)
        assert result.exit_status == 1 and "needs an approved request" in result.stderr
        conn.close()
    finally:
        await client.patch(
            f"/accounts/{lab['account']['id']}", headers=admin, json={"requires_approval": False}
        )


async def test_admin_can_kill_a_live_session(gateway, lab, client, admin):
    conn = await _connect(gateway, f"netops1%{DEVICE_USER}%fake-rtr", "User-Passw0rd-netops1")
    proc = await conn.create_process(term_type="xterm")
    await _read_until(proc.stdout, "fake-rtr# ")
    sid = str((await _latest_session("netops1"))["id"])

    resp = await client.post(f"/sessions/{sid}/terminate", headers=admin)
    assert resp.status_code == 200
    out = await _read_until(proc.stdout, "Terminated by an administrator")
    assert "Disconnecting" in out
    await asyncio.wait_for(proc.wait_closed(), 5)
    conn.close()
    row = await _wait_closed("netops1")
    assert row["status"] == "terminated"


async def test_host_key_mismatch_never_sends_the_credential(gateway, lab, device, client, admin):
    other = asyncssh.generate_private_key("ssh-ed25519")
    async with session_factory()() as s:
        await s.execute(
            text("UPDATE inventory.targets SET ssh_host_key = :k WHERE id = :id"),
            {"k": other.export_public_key("openssh").decode().strip(), "id": lab["target"]["id"]},
        )
        await s.commit()
    logins_before = len(device.logins)

    conn = await _connect(gateway, f"netops1%{DEVICE_USER}%fake-rtr", "User-Passw0rd-netops1")
    result = await conn.run("show version", timeout=10)
    conn.close()
    assert "HOST KEY MISMATCH" in result.stdout
    assert len(device.logins) == logins_before

    # After an admin resets the pin, the next session learns the real key again.
    resp = await client.post(f"/targets/{lab['target']['id']}/host-key/reset", headers=admin)
    assert resp.status_code == 200 and resp.json()["data"]["ssh_host_key_fingerprint"] is None
    conn = await _connect(gateway, f"netops1%{DEVICE_USER}%fake-rtr", "User-Passw0rd-netops1")
    assert "FakeOS" in (await conn.run("show version", timeout=5)).stdout
    conn.close()


async def test_exclusive_account_held_by_someone_else(gateway, lab, client, admin, make_user):
    other = await make_user("holder1")
    resp = await client.post(
        "/checkouts",
        headers=other,
        json={"account_id": lab["account"]["id"], "reason": "maintenance window"},
    )
    assert resp.status_code == 201
    try:
        conn = await _connect(gateway, f"netops1%{DEVICE_USER}%fake-rtr", "User-Passw0rd-netops1")
        result = await conn.run("show version", timeout=5)
        conn.close()
        assert result.exit_status == 1 and "held by holder1" in result.stderr
    finally:
        await client.post(f"/checkouts/{resp.json()['data']['id']}/checkin", headers=other)


async def test_gateway_events_keep_the_audit_chain_valid(client, admin):
    data = (await client.post("/audit/verify", headers=admin)).json()["data"]
    assert data["ok"] is True
    actions = {
        e["action"]
        for e in (
            await client.get("/audit/events", headers=admin, params={"page_size": 200})
        ).json()["data"]
    }
    assert {
        "session.start",
        "secret.inject",
        "session.command_blocked",
        "session.terminate",
        "session.end",
        "target.host_key_learned",
        "target.host_key_mismatch",
    } <= actions
