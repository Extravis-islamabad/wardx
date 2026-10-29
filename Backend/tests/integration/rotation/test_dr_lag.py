"""DR lag rotation safety (HA_DR.md §6.1, with the explicit dr_site_configured setting).

The lag source (pg_stat_replication) is patched; no lab or replica is needed.
"""

from __future__ import annotations

import pytest

from src.contracts.dto.health.cluster_dto import ReplicaDTO
from src.core.config import get_settings
from src.repositories.health.cluster_repository import ClusterRepository
from src.scheduler.jobs import rotation_tick
from tests.integration.ha.ha_support import open_alerts, rows
from tests.integration.rotation.rotation_support import sql

pytestmark = pytest.mark.asyncio(loop_scope="session")

KIND = "cluster.dr_lag_high"


@pytest.fixture
def lag(monkeypatch):
    """Set what pg_stat_replication reports: a list of rows, or an exception."""
    state: dict = {"rows": []}

    async def fake(self):
        if isinstance(state["rows"], Exception):
            raise state["rows"]
        return list(state["rows"])

    monkeypatch.setattr(ClusterRepository, "replicas", fake)
    return state


@pytest.fixture
def dr_on(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "dr_site_configured", True)
    monkeypatch.setattr(settings, "dr_replica_name", "dr1")
    monkeypatch.setattr(settings, "dr_max_lag_seconds", 60)
    return settings


def replica(seconds: float | None, name: str = "dr1") -> ReplicaDTO:
    return ReplicaDTO(name, "streaming", "async", seconds, 0 if seconds is not None else 4096)


async def _scheduled_job(rotlab) -> tuple[str, str]:
    account = await rotlab.account()
    job = (
        await sql(
            "INSERT INTO access.rotation_jobs (account_id, target_id, reason, status, not_before) "
            "VALUES (:a, :t, 'schedule', 'pending', NOW() - INTERVAL '1 minute') RETURNING id",
            a=account["id"],
            t=account["target"]["id"],
        )
    )[0]["id"]
    return account["id"], str(job)


async def _status(job_id: str) -> str:
    return (await sql("SELECT status FROM access.rotation_jobs WHERE id = :i", i=job_id))[0][
        "status"
    ]


async def test_no_dr_site_no_pause_no_alert_no_warning(rotlab, client, admin, lag):
    lag["rows"] = []  # nothing replicates: would be "unreadable" if a DR site were configured
    before = await open_alerts(KIND)
    _, job_id = await _scheduled_job(rotlab)
    out = await rotation_tick(get_settings())
    assert out["dr_paused"] == 0
    assert await _status(job_id) == "succeeded"
    assert await open_alerts(KIND) == before
    account = await rotlab.account()
    job = await rotlab.request(account["id"])
    assert job["dr_lag_warning"] is None
    view = (await client.get(f"/accounts/{account['id']}/rotation", headers=admin)).json()
    assert view["data"]["dr_lag_warning"] is None
    cluster = (await client.get("/health/cluster", headers=admin)).json()["data"]
    assert cluster["dr_site_configured"] is False and cluster["dr"]["state"] == "not_configured"
    await rotlab.run(job["id"])


async def test_lag_within_limit_does_not_pause(rotlab, lag, dr_on):
    lag["rows"] = [replica(5.0)]
    _, job_id = await _scheduled_job(rotlab)
    out = await rotation_tick(dr_on)
    assert out["dr_paused"] == 0
    assert await _status(job_id) == "succeeded"


async def test_high_lag_pauses_alerts_warns_and_recovery_lifts_it(
    rotlab, client, admin, lag, dr_on
):
    before = await open_alerts(KIND)
    lag["rows"] = [replica(300.0)]
    _, job_id = await _scheduled_job(rotlab)
    out = await rotation_tick(dr_on)
    assert out["dr_paused"] == 1
    assert await _status(job_id) == "pending"  # queued scheduled job waits
    assert await open_alerts(KIND) == before + 1
    await rotation_tick(dr_on)  # still high: one alert, not two
    assert await open_alerts(KIND) == before + 1

    # On-demand rotation still runs, with the warning, audited.
    account = await rotlab.account()
    view = (await client.get(f"/accounts/{account['id']}/rotation", headers=admin)).json()
    assert "behind" in view["data"]["dr_lag_warning"]
    manual = await rotlab.request(account["id"])
    assert "300s behind" in manual["dr_lag_warning"]
    assert (await rotlab.run(manual["id"]))["status"] == "succeeded"
    flagged = await rows(
        "SELECT details->>'dr_lag_warning' FROM audit.events WHERE object_id = :i "
        "AND action = 'rotation.request_rotate'",
        i=manual["id"],
    )
    assert flagged == [("true",)]
    cluster = (await client.get("/health/cluster", headers=admin)).json()["data"]
    assert cluster["dr"]["rotation_paused"] is True and cluster["dr"]["state"] == "high"

    # Recovered: the pause lifts, the alert clears, the held job runs.
    lag["rows"] = [replica(2.0)]
    out = await rotation_tick(dr_on)
    assert out["dr_paused"] == 0
    assert await open_alerts(KIND) == before
    assert await _status(job_id) == "succeeded"


@pytest.mark.parametrize(
    "case", ["replica_missing", "query_error", "name_missing", "lag_null_behind"]
)
async def test_unreadable_lag_pauses_with_alert(rotlab, lag, dr_on, monkeypatch, case):
    before = await open_alerts(KIND)
    if case == "replica_missing":
        lag["rows"] = [replica(1.0, name="some-other-standby")]
    elif case == "query_error":
        lag["rows"] = RuntimeError("permission denied for pg_stat_replication")
    elif case == "name_missing":
        lag["rows"] = [replica(1.0)]
        monkeypatch.setattr(dr_on, "dr_replica_name", "")
    else:
        lag["rows"] = [replica(None)]
    _, job_id = await _scheduled_job(rotlab)
    out = await rotation_tick(dr_on)
    assert out["dr_paused"] == 1
    assert await _status(job_id) == "pending"
    assert await open_alerts(KIND) == before + 1
    # Recover, so the next case starts clean.
    monkeypatch.setattr(dr_on, "dr_replica_name", "dr1")
    lag["rows"] = [replica(0.5)]
    assert (await rotation_tick(dr_on))["dr_paused"] == 0
    assert await open_alerts(KIND) == before
    assert await _status(job_id) == "succeeded"
