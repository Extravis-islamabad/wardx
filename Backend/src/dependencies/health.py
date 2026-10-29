"""Health and cluster service providers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.dependencies.audit import build_audit_service
from src.dependencies.database import SQLSessionDep
from src.repositories.health.cluster_repository import ClusterRepository
from src.repositories.health.health_repository import HealthRepository
from src.services.health.cluster_service import ClusterService
from src.services.health.health_service import HealthService


def build_health_service(session: AsyncSession) -> HealthService:
    return HealthService(HealthRepository(session))


async def get_health_service(session: SQLSessionDep) -> HealthService:
    return build_health_service(session)


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]


def build_cluster_service(session: AsyncSession) -> ClusterService:
    from src.dependencies.identity import build_alert_service

    return ClusterService(
        ClusterRepository(session),
        build_alert_service(session),
        build_audit_service(session),
        get_settings(),
    )


async def get_cluster_service(session: SQLSessionDep) -> ClusterService:
    return build_cluster_service(session)


ClusterServiceDep = Annotated[ClusterService, Depends(get_cluster_service)]
