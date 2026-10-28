"""Seals and opens secret versions through the key provider.

The provider is loaded once at startup (src/keys/runtime.py); until then the
vault is sealed and every read or write fails. Callers hold the owner row lock
while storing, so version numbers cannot race.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from src.errors.exceptions import NotFoundError, VaultError
from src.keys.provider import KeyProvider
from src.repositories.vault.secret_repository import SecretRepository
from src.vault.envelope import VaultIntegrityError, VaultKeyError, open_sealed, seal, secret_aad


class VaultService:
    def __init__(self, repo: SecretRepository, provider: KeyProvider) -> None:
        self._repo = repo
        self._provider = provider

    async def store(
        self,
        *,
        owner_type: str,
        owner_id: uuid.UUID,
        version: int,
        plaintext: str,
        created_by: uuid.UUID | None,
        status: str | None = "current",
    ) -> None:
        """Store a version. ``status`` 'current' relabels the old current 'previous'
        (labels only: the owner row's version pointer decides what is current)."""
        sealed = await seal(
            self._provider, plaintext.encode(), secret_aad(owner_type, owner_id, version)
        )
        if status == "current":
            await self._repo.demote_current(owner_type, owner_id)
        await self._repo.add(
            owner_type=owner_type,
            owner_id=owner_id,
            version=version,
            sealed=sealed,
            created_by=created_by,
            status=status,
        )

    async def label(self, owner_type: str, owner_id: uuid.UUID, version: int, status: str) -> None:
        """Relabel one version; 'current' first relabels the old current 'previous'."""
        if status == "current":
            await self._repo.demote_current(owner_type, owner_id)
        await self._repo.set_status(owner_type, owner_id, version, status)

    async def labels(self, owner_type: str, owner_id: uuid.UUID) -> dict[int, str | None]:
        return await self._repo.statuses(owner_type, owner_id)

    async def read(self, *, owner_type: str, owner_id: uuid.UUID, version: int) -> str:
        sealed = await self._repo.get(owner_type, owner_id, version)
        if sealed is None:
            raise NotFoundError("Secret version not found")
        try:
            plaintext = await open_sealed(
                self._provider, sealed, secret_aad(owner_type, owner_id, version)
            )
            return plaintext.decode()
        except (VaultKeyError, VaultIntegrityError) as exc:
            raise VaultError("Secret could not be decrypted", {"reason": str(exc)}) from exc

    async def next_version(self, owner_type: str, owner_id: uuid.UUID) -> int:
        return await self._repo.max_version(owner_type, owner_id) + 1

    async def shred(self, owner_type: str, owner_ids: Sequence[uuid.UUID]) -> None:
        """Delete every version of these owners' secrets."""
        await self._repo.delete_for_owners(owner_type, owner_ids)
