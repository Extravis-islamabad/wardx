"""Dashboard service provider."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.dependencies.database import SQLSessionDep
from src.repositories.dashboard.dashboard_repository import DashboardRepository
from src.services.dashboard.dashboard_service import DashboardService


def build_dashboard_service(session: AsyncSession) -> DashboardService:
    return DashboardService(DashboardRepository(session))


async def get_dashboard_service(session: SQLSessionDep) -> DashboardService:
    return build_dashboard_service(session)


DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]
