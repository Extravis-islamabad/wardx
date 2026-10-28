"""Vault service provider."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.dependencies.database import SQLSessionDep
from src.repositories.vault.secret_repository import SecretRepository
from src.services.vault.vault_service import VaultService


def build_vault_service(session: AsyncSession) -> VaultService:
    return VaultService(SecretRepository(session))


async def get_vault_service(session: SQLSessionDep) -> VaultService:
    return build_vault_service(session)


VaultServiceDep = Annotated[VaultService, Depends(get_vault_service)]
