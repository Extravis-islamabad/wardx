"""/health/cluster and the degraded-synchronous-replication alert (HA_DR.md §3)."""

from __future__ import annotations

import pytest

from src.services.health.cluster_service import condition_object_id
from tests.integration.ha.ha_support import open_alerts, rows, run_check, scalar, streaming

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_cluster_endpoint_is_admin_only(client, admin, make_user):
    resp = await client.get("/health/cluster", headers=admin)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["replication"]["in_recovery"] is False
    assert data["replication"]["sync_state"] == "standalone"
    assert data["dr_site_configured"] is False
    assert data["dr"]["state"] == "not_configured"
    assert data["dr"]["rotation_paused"] is False
    auditor = await make_user("cluster-auditor", role="auditor")
    assert (await client.get("/health/cluster", headers=auditor)).status_code == 403
    assert (await client.get("/health/cluster")).status_code == 401


async def test_degraded_sync_alert_raised_and_cleared(monkeypatch, app):
    kind = "cluster.sync_degraded"
    before = await open_alerts(kind)
    # Expected but missing: degraded, one high alert, audited.
    out, *_ = await run_check(monkeypatch, [], ha_expect_sync_standby=True)
    assert out["sync_state"] == "degraded"
    assert await open_alerts(kind) == before + 1
    # Still degraded: no second alert.
    await run_check(monkeypatch, [streaming("standby1")], ha_expect_sync_standby=True)
    assert await open_alerts(kind) == before + 1
    assert await scalar("SELECT active FROM ha.conditions WHERE kind = 'sync_degraded'")
    # A synchronous standby is back: the alert is cleared (acknowledged by the system).
    out, *_ = await run_check(
        monkeypatch, [streaming("standby1", "sync")], ha_expect_sync_standby=True
    )
    assert out["sync_state"] == "sync"
    assert await open_alerts(kind) == before
    assert not await scalar("SELECT active FROM ha.conditions WHERE kind = 'sync_degraded'")
    actions = [
        a
        for (a,) in await rows(
            "SELECT action FROM audit.events WHERE object_id = :o ORDER BY seq",
            o=condition_object_id("sync_degraded"),
        )
    ]
    assert actions[-2:] == ["cluster.sync_degraded", "cluster.sync_restored"]


async def test_quorum_counts_as_sync_and_unexpected_is_quiet(monkeypatch, app):
    out, *_ = await run_check(monkeypatch, [streaming("s1", "quorum")], ha_expect_sync_standby=True)
    assert out["sync_state"] == "sync"
    out, *_ = await run_check(monkeypatch, [streaming("s1")], ha_expect_sync_standby=False)
    assert out["sync_state"] == "async"
