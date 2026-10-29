"""Responses for /health/cluster (HA_DR.md §3, §4, §5, §6.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class LeaderResponse(BaseModel):
    node: str
    term: int
    elected_at: datetime
    last_seen: datetime
    fresh: bool


class ReplicaResponse(BaseModel):
    application_name: str
    state: str | None
    sync_state: str | None
    replay_lag_seconds: float | None
    lag_bytes: int | None


class ReplicationResponse(BaseModel):
    in_recovery: bool
    sync_state: str
    expect_sync_standby: bool
    replicas: list[ReplicaResponse]
    error: str | None


class DrResponse(BaseModel):
    site_configured: bool
    replica_name: str | None
    state: str
    lag_seconds: float | None
    max_lag_seconds: int
    reason: str | None
    rotation_paused: bool


class ConditionResponse(BaseModel):
    kind: str
    active: bool
    since: datetime
    checked_at: datetime
    details: dict[str, Any]


class GatewayNodeResponse(BaseModel):
    node: str
    started_at: datetime
    last_seen: datetime
    host_key_fingerprint: str
    stopped_at: datetime | None
    fresh: bool


class RestoreDrillResponse(BaseModel):
    ran_at: datetime
    ok: bool
    restore_point: datetime | None


class ClusterResponse(BaseModel):
    node: str
    leader: LeaderResponse | None
    replication: ReplicationResponse
    dr: DrResponse
    dr_site_configured: bool
    conditions: list[ConditionResponse]
    gateways: list[GatewayNodeResponse]
    gateway_host_keys_consistent: bool
    last_restore_drill: RestoreDrillResponse | None = None
