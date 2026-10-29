"""Cluster health: leadership records, synchronous replication, DR lag (HA_DR.md §3, §4, §6.1).

The leader's ``check`` tracks two conditions in ha.conditions:

- ``sync_degraded``: a synchronous standby is expected (WARDX_HA_EXPECT_SYNC_STANDBY) and
  none is attached, so commits run asynchronous. High alert while active; the alert is
  acknowledged by the system when a synchronous standby is back.
- ``dr_lag``: only with a DR site configured (WARDX_DR_SITE_CONFIGURED). The DR replica's
  replay lag is over WARDX_DR_MAX_LAG_SECONDS, or unreadable (fail safe). Scheduled
  rotations pause while it is active.

Without a DR site nothing about DR is ever raised: the dashboard shows it as information.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import structlog

from src.contracts.dto.health.cluster_dto import (
    ASYNC,
    COND_DR_LAG,
    COND_SYNC_DEGRADED,
    DEGRADED,
    DR_HIGH,
    DR_NOT_CONFIGURED,
    DR_OK,
    DR_UNREADABLE,
    STANDALONE,
    SYNC,
    ClusterDTO,
    DrStateDTO,
    ReplicaDTO,
    ReplicationDTO,
)
from src.core.config import Settings
from src.core.context import SYSTEM_ACTOR
from src.models import utcnow
from src.repositories.health.cluster_repository import ClusterRepository
from src.services.audit.audit_service import AuditService
from src.services.security.alert_service import AlertService

logger = structlog.get_logger(__name__)

_SYNC_STATES = ("sync", "quorum")


def condition_object_id(kind: str) -> uuid.UUID:
    """A stable id per condition, so its alerts are found and acknowledged on recovery."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"wardx:ha:{kind}")


def sync_state(replicas: list[ReplicaDTO], *, expected: bool) -> str:
    if any(r.state == "streaming" and r.sync_state in _SYNC_STATES for r in replicas):
        return SYNC
    if expected:
        return DEGRADED
    return ASYNC if replicas else STANDALONE


def dr_state(
    settings: Settings, replicas: list[ReplicaDTO] | None, error: str | None = None
) -> DrStateDTO:
    """The DR replica's lag from pg_stat_replication rows; anything unreadable fails safe."""
    name = settings.dr_replica_name or None
    base = {"replica_name": name, "max_lag_seconds": settings.dr_max_lag_seconds}
    if not settings.dr_site_configured:
        return DrStateDTO(configured=False, state=DR_NOT_CONFIGURED, **base)

    def unreadable(reason: str) -> DrStateDTO:
        return DrStateDTO(configured=True, state=DR_UNREADABLE, reason=reason, **base)

    if name is None:
        return unreadable("WARDX_DR_REPLICA_NAME is not set")
    if error is not None or replicas is None:
        return unreadable(f"replication status could not be read: {error or 'no answer'}")
    row = next((r for r in replicas if r.application_name == name), None)
    if row is None:
        return unreadable(f"DR replica '{name}' is not in pg_stat_replication")
    lag = row.replay_lag_seconds
    if lag is None:
        # PostgreSQL clears replay_lag once a replica has fully caught up and WAL is idle.
        if row.lag_bytes == 0 and row.state == "streaming":
            lag = 0.0
        else:
            return unreadable(f"DR replica '{name}' reports no replay lag ({row.state})")
    state = DR_HIGH if lag > settings.dr_max_lag_seconds else DR_OK
    reason = (
        f"DR replica '{name}' is {lag:.0f}s behind (limit {settings.dr_max_lag_seconds}s)"
        if state == DR_HIGH
        else None
    )
    return DrStateDTO(configured=True, state=state, lag_seconds=lag, reason=reason, **base)


DR_LAG_WARNING = (
    "The DR replica is behind ({detail}). A rotation committed now could be lost if the "
    "primary site is lost before it replicates; the device would then hold a password the DR "
    "vault does not know. Run 'wardx dr post-failover-check' after any DR activation."
)


class ClusterService:
    def __init__(
        self,
        repo: ClusterRepository,
        alerts: AlertService,
        audit: AuditService,
        settings: Settings,
    ) -> None:
        self._repo = repo
        self._alerts = alerts
        self._audit = audit
        self._settings = settings

    # ── Reading ──

    async def replication(self) -> ReplicationDTO:
        try:
            in_recovery = await self._repo.in_recovery()
            replicas = await self._repo.replicas()
        except Exception as exc:  # a broken view must not break health or fail open
            await self._repo.rollback()
            return ReplicationDTO(False, [], DEGRADED, error=type(exc).__name__)
        expected = self._settings.ha_expect_sync_standby
        return ReplicationDTO(in_recovery, replicas, sync_state(replicas, expected=expected))

    async def dr(self, replication: ReplicationDTO | None = None) -> DrStateDTO:
        if not self._settings.dr_site_configured:
            return dr_state(self._settings, [])
        replication = replication or await self.replication()
        return dr_state(self._settings, replication.replicas, replication.error)

    async def dr_lag_warning(self) -> str | None:
        """For on-demand rotation: a warning while the DR lag is high or unreadable."""
        state = await self.dr()
        if not state.rotation_paused:
            return None
        return DR_LAG_WARNING.format(detail=state.reason or state.state)

    async def overview(self, node: str) -> ClusterDTO:
        replication = await self.replication()
        leader = await self._repo.leader()
        stale_after = timedelta(seconds=max(self._settings.leader_interval_seconds * 3, 15))
        fresh = leader is not None and utcnow() - leader.last_seen <= stale_after
        return ClusterDTO(
            node=node,
            leader=leader,
            leader_fresh=fresh,
            replication=replication,
            dr=await self.dr(replication),
            conditions=await self._repo.conditions(),
        )

    # ── Leadership records (the advisory lock decides; these are for people) ──

    async def record_elected(self, node: str) -> int:
        term, previous = await self._repo.claim_leader_row(node, utcnow())
        await self._audit.record(
            SYSTEM_ACTOR,
            "scheduler.leader_elected",
            object_type="cluster",
            details={"node": node, "previous": previous, "term": term},
        )
        await self._repo.commit()
        return term

    async def record_released(self, node: str, reason: str) -> None:
        await self._audit.record(
            SYSTEM_ACTOR,
            "scheduler.leader_released",
            object_type="cluster",
            details={"node": node, "reason": reason},
        )
        await self._repo.commit()

    # ── The leader's check: conditions, alerts ──

    async def check(self) -> dict[str, Any]:
        replication = await self.replication()
        dr = await self.dr(replication)
        sync_bad = self._settings.ha_expect_sync_standby and replication.sync_state != SYNC
        await self._set_condition(
            COND_SYNC_DEGRADED,
            active=sync_bad,
            details={
                "sync_state": replication.sync_state,
                "standbys": [r.application_name for r in replication.replicas],
            },
            raise_kind="cluster.sync_degraded",
            raise_message=(
                "No synchronous standby is attached: the primary is committing asynchronously, "
                "so a failover now could lose the latest commits (HA_DR.md §3)"
            ),
            clear_kind="cluster.sync_restored",
        )
        await self._set_condition(
            COND_DR_LAG,
            active=dr.rotation_paused,
            details={"state": dr.state, "lag_seconds": dr.lag_seconds, "reason": dr.reason},
            raise_kind="cluster.dr_lag_high",
            raise_message=(
                f"DR replication lag is {dr.state}: {dr.reason or ''}. Scheduled rotations are "
                "paused until it recovers (HA_DR.md §6.1)"
            ),
            clear_kind="cluster.dr_lag_recovered",
        )
        await self._repo.commit()
        return {
            "sync_state": replication.sync_state,
            "dr_state": dr.state,
            "rotation_paused": dr.rotation_paused,
        }

    async def _set_condition(
        self,
        kind: str,
        *,
        active: bool,
        details: dict[str, Any],
        raise_kind: str,
        raise_message: str,
        clear_kind: str,
    ) -> None:
        now = utcnow()
        current = await self._repo.condition(kind)
        was_active = bool(current and current.active)
        alert_id = current.alert_id if current else None
        since = current.since if current and current.active == active else now
        object_id = condition_object_id(kind)
        if active and not was_active:
            alert = await self._alerts.raise_alert(
                SYSTEM_ACTOR,
                kind=raise_kind,
                message=raise_message,
                object_type="cluster",
                object_id=object_id,
                details=details,
            )
            alert_id = alert.id
            await self._audit.record(
                SYSTEM_ACTOR,
                raise_kind,
                object_type="cluster",
                object_id=object_id,
                outcome="failure",
                details=details,
            )
            logger.warning(raise_kind, **{k: v for k, v in details.items() if k != "standbys"})
        elif was_active and not active:
            cleared = await self._alerts.clear(raise_kind, object_id)
            await self._audit.record(
                SYSTEM_ACTOR,
                clear_kind,
                object_type="cluster",
                object_id=object_id,
                details={**details, "alerts_cleared": len(cleared)},
            )
            alert_id = None
            logger.info(clear_kind)
        if current is None and not active:
            if kind == COND_DR_LAG and not self._settings.dr_site_configured:
                return  # nothing to track without a DR site
        await self._repo.put_condition(
            kind, active=active, since=since, now=now, details=details, alert_id=alert_id
        )
