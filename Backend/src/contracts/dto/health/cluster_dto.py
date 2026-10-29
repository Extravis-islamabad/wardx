"""Cluster DTOs: scheduler leadership, replication, DR lag, gateway nodes (HA_DR.md)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Synchronous replication states (§3).
SYNC = "sync"  # a synchronous standby is attached and streaming
DEGRADED = "degraded"  # one is expected and none is attached: running asynchronous
ASYNC = "async"  # standbys stream, none synchronous, none expected
STANDALONE = "standalone"  # no standby at all, none expected

# DR lag states (§6.1).
DR_NOT_CONFIGURED = "not_configured"
DR_OK = "ok"
DR_HIGH = "high"
DR_UNREADABLE = "unreadable"

# Condition kinds (ha.conditions).
COND_SYNC_DEGRADED = "sync_degraded"
COND_DR_LAG = "dr_lag"


@dataclass(frozen=True)
class LeaderDTO:
    node: str
    term: int
    elected_at: datetime
    last_seen: datetime


@dataclass(frozen=True)
class ReplicaDTO:
    application_name: str
    state: str | None
    sync_state: str | None
    replay_lag_seconds: float | None
    lag_bytes: int | None


@dataclass(frozen=True)
class ConditionDTO:
    kind: str
    active: bool
    since: datetime
    checked_at: datetime
    details: dict[str, Any]
    alert_id: uuid.UUID | None


@dataclass(frozen=True)
class ReplicationDTO:
    in_recovery: bool
    replicas: list[ReplicaDTO]
    sync_state: str
    error: str | None = None


@dataclass(frozen=True)
class DrStateDTO:
    configured: bool
    replica_name: str | None
    max_lag_seconds: int
    state: str
    lag_seconds: float | None = None
    reason: str | None = None

    @property
    def rotation_paused(self) -> bool:
        return self.configured and self.state in (DR_HIGH, DR_UNREADABLE)


@dataclass(frozen=True)
class GatewayNodeDTO:
    node: str
    started_at: datetime
    last_seen: datetime
    host_key_fingerprint: str
    stopped_at: datetime | None
    fresh: bool = False


@dataclass(frozen=True)
class ClusterDTO:
    node: str
    leader: LeaderDTO | None
    leader_fresh: bool
    replication: ReplicationDTO
    dr: DrStateDTO
    conditions: list[ConditionDTO] = field(default_factory=list)
    gateways: list[GatewayNodeDTO] = field(default_factory=list)
    gateway_host_keys_consistent: bool = True
    last_restore_drill: dict[str, Any] | None = None
