"""Headline counts for the home page: estate-wide, plus the actor's own."""

from __future__ import annotations

from src.contracts.dto.dashboard.dashboard_dto import DashboardSummaryDTO
from src.core.context import Actor
from src.repositories.dashboard.dashboard_repository import DashboardRepository


class DashboardService:
    def __init__(self, repo: DashboardRepository) -> None:
        self._repo = repo

    async def summary(self, actor: Actor) -> DashboardSummaryDTO:
        return await self._repo.summary(actor.id)
