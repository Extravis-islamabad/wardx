"""Health service provider."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.dependencies.database import SQLSessionDep
from src.repositories.health.health_repository import HealthRepository
from src.services.health.health_service import HealthService


def build_health_service(session: AsyncSession) -> HealthService:
    return HealthService(HealthRepository(session))


async def get_health_service(session: SQLSessionDep) -> HealthService:
    return build_health_service(session)


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]
