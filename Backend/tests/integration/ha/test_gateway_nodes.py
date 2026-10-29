"""Gateway heartbeats, the lost-node sweep and the shared host key check (HA_DR.md §5)."""

from __future__ import annotations

import asyncio

import asyncssh
import pytest

from src.gateway.server import Gateway
from src.scheduler.jobs import gateway_sweep
from src.services.sessions.gateway_node_service import NODE_LOST_REASON, HostKeyConflict
from tests.conftest import DEVICE_USER
from tests.integration.ha.ha_support import execute, rows, scalar

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _node(gateway, name: str, **overrides) -> Gateway:
    settings = gateway.settings.model_copy(
        update={"gateway_node": name, "gateway_heartbeat_seconds": 0.2, **overrides}
    )
    return Gateway(settings)


async def _ssh(port: int) -> asyncssh.SSHClientConnection:
    return await asyncssh.connect(
        "127.0.0.1",
        port,
        username=f"netops1%{DEVICE_USER}%fake-rtr",
        password="User-Passw0rd-netops1",
        known_hosts=None,
        client_keys=None,
        agent_path=None,
        config=None,
        preferred_auth="password",
    )


async def test_nodes_heartbeat_and_share_one_host_key(gateway, lab, tmp_path):
    other = _node(gateway, "gw-b")
    await other.start()
    try:
        assert other.host_key_fingerprint == gateway.host_key_fingerprint
        seen = await scalar("SELECT last_seen FROM ha.gateway_nodes WHERE node = 'gw-b'")
        await asyncio.sleep(0.6)
        assert await scalar("SELECT last_seen FROM ha.gateway_nodes WHERE node = 'gw-b'") > seen
        # A node with its own key refuses to start while the others are live.
        stray = _node(gateway, "gw-stray", gateway_host_key_file=str(tmp_path / "other_key"))
        with pytest.raises(HostKeyConflict):
            await stray.start()
        assert await scalar("SELECT count(*) FROM ha.gateway_nodes WHERE node = 'gw-stray'") == 0
        # An expected fingerprint is enforced too.
        pinned = _node(gateway, "gw-pinned", gateway_host_key_fingerprint="SHA256:not-this-one")
        with pytest.raises(HostKeyConflict):
            await pinned.start()
    finally:
        await other.stop()
    assert await scalar("SELECT stopped_at FROM ha.gateway_nodes WHERE node = 'gw-b'")


async def test_lost_node_sessions_terminated_and_checkouts_closed(gateway, lab, client, admin):
    node = _node(gateway, "gw-lost")
    await node.start()
    conn = await _ssh(node.port)
    try:
        proc = await conn.create_process(term_type="xterm", term_size=(100, 30))
        await asyncio.wait_for(proc.stdout.read(200), 5)
        sid, checkout_id = (
            await rows(
                "SELECT id, checkout_id FROM access.sessions WHERE gateway_node = 'gw-lost' "
                "AND status = 'active'"
            )
        )[0]
        assert await scalar("SELECT owns_checkout FROM access.sessions WHERE id = :i", i=sid)

        # The node dies: no more heartbeats, nothing finishes the session.
        node._heartbeat.cancel()
        node._watcher.cancel()
        await execute(
            "UPDATE ha.gateway_nodes SET last_seen = now() - interval '1 hour' "
            "WHERE node = 'gw-lost'"
        )
        settings = gateway.settings.model_copy(update={"gateway_lost_seconds": 30})
        assert await gateway_sweep(settings) == 1
        assert await gateway_sweep(settings) == 0  # idempotent

        status, reason = (
            await rows("SELECT status, close_reason FROM access.sessions WHERE id = :i", i=sid)
        )[0]
        assert (status, reason) == ("terminated", NODE_LOST_REASON)
        assert (
            await scalar("SELECT status FROM access.checkouts WHERE id = :i", i=checkout_id)
            == "returned"
        )
        ends = await rows(
            "SELECT details->>'reason', safe_id FROM audit.events "
            "WHERE action = 'session.end' AND object_id = :i",
            i=sid,
        )
        assert len(ends) == 1 and ends[0][0] == NODE_LOST_REASON and ends[0][1] is not None
        assert await scalar(
            "SELECT count(*) FROM audit.events WHERE action = 'checkout.return' AND object_id = :i",
            i=checkout_id,
        )
        # The healthy node is listed in /health/cluster, the lost one is not fresh.
        data = (await client.get("/health/cluster", headers=admin)).json()["data"]
        by_node = {g["node"]: g for g in data["gateways"]}
        assert by_node["gw-lost"]["fresh"] is False
        assert by_node["test-gw"]["fresh"] is True
        assert data["gateway_host_keys_consistent"] is True
    finally:
        conn.close()
        await node.stop()
    # The cut-off node finishing late does not end or audit the session a second time.
    await asyncio.sleep(0.5)
    assert (
        await scalar(
            "SELECT count(*) FROM audit.events WHERE action = 'session.end' AND object_id = :i",
            i=sid,
        )
        == 1
    )
