"""Helpers for the HA tests on the plain test database (no lab)."""

from __future__ import annotations

from sqlalchemy import text

from src.contracts.dto.health.cluster_dto import ReplicaDTO
from src.core.config import get_settings
from src.core.db import session_factory
from src.dependencies.audit import build_audit_service
from src.dependencies.identity import build_alert_service
from src.repositories.health.cluster_repository import ClusterRepository
from src.services.health.cluster_service import ClusterService


async def scalar(sql: str, **params):
    async with session_factory()() as s:
        return (await s.execute(text(sql), params)).scalar()


async def rows(sql: str, **params):
    async with session_factory()() as s:
        return (await s.execute(text(sql), params)).all()


def streaming(name: str, sync_state: str = "async", lag: float | None = 0.5) -> ReplicaDTO:
    return ReplicaDTO(name, "streaming", sync_state, lag, 0 if lag is not None else 1024)


async def run_check(monkeypatch, replicas, **overrides):
    """ClusterService.check() with these pg_stat_replication rows and settings."""

    async def fake_replicas(self):
        if isinstance(replicas, Exception):
            raise replicas
        return list(replicas)

    monkeypatch.setattr(ClusterRepository, "replicas", fake_replicas)
    settings = get_settings().model_copy(update=overrides)
    async with session_factory()() as session:
        service = ClusterService(
            ClusterRepository(session),
            build_alert_service(session),
            build_audit_service(session),
            settings,
        )
        return await service.check(), service, settings


async def open_alerts(kind: str) -> int:
    return await scalar(
        "SELECT count(*) FROM security.alerts WHERE kind = :k AND acknowledged_at IS NULL", k=kind
    )
