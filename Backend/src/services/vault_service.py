"""Transitional shim over VaultService for modules not yet on the layered services."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.vault.secret_repository import SecretRepository
from src.services.vault.vault_service import VaultService, keyring, set_keyring

__all__ = ["keyring", "read", "set_keyring", "store"]


async def store(
    session: AsyncSession,
    *,
    owner_type: str,
    owner_id: uuid.UUID,
    version: int,
    plaintext: str,
    created_by: uuid.UUID | None,
) -> None:
    await VaultService(SecretRepository(session)).store(
        owner_type=owner_type,
        owner_id=owner_id,
        version=version,
        plaintext=plaintext,
        created_by=created_by,
    )


async def read(session: AsyncSession, *, owner_type: str, owner_id: uuid.UUID, version: int) -> str:
    return await VaultService(SecretRepository(session)).read(
        owner_type=owner_type, owner_id=owner_id, version=version
    )
