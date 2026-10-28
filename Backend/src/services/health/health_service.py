"""Readiness: the database answers and the vault is unsealed."""

from __future__ import annotations

from src.keys.runtime import key_provider
from src.repositories.health.health_repository import HealthRepository


class HealthService:
    def __init__(self, repo: HealthRepository) -> None:
        self._repo = repo

    async def readiness(self) -> dict[str, str]:
        """Raises when the database is unreachable or the vault is sealed."""
        await self._repo.ping()
        await key_provider().health()  # raises when the vault is sealed
        return {"database": "ok", "vault": "unsealed"}
