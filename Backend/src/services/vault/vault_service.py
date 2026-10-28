"""Seals and opens secret versions with the process keyring.

The keyring is loaded once at startup (``set_keyring``); until then the vault
is sealed and every read or write fails. Callers hold the owner row lock while
storing, so version numbers cannot race.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from src.errors.exceptions import NotFoundError, VaultError
from src.repositories.vault.secret_repository import SecretRepository
from src.vault.envelope import (
    Keyring,
    VaultIntegrityError,
    VaultKeyError,
    open_sealed,
    seal,
    secret_aad,
)

_keyring: Keyring | None = None


def set_keyring(keyring: Keyring) -> None:
    global _keyring
    _keyring = keyring


def keyring() -> Keyring:
    if _keyring is None:
        raise VaultError("Vault is sealed: no key loaded")
    return _keyring


class VaultService:
    def __init__(self, repo: SecretRepository) -> None:
        self._repo = repo

    async def store(
        self,
        *,
        owner_type: str,
        owner_id: uuid.UUID,
        version: int,
        plaintext: str,
        created_by: uuid.UUID | None,
    ) -> None:
        sealed = seal(keyring(), plaintext.encode(), secret_aad(owner_type, owner_id, version))
        await self._repo.add(
            owner_type=owner_type,
            owner_id=owner_id,
            version=version,
            sealed=sealed,
            created_by=created_by,
        )

    async def read(self, *, owner_type: str, owner_id: uuid.UUID, version: int) -> str:
        sealed = await self._repo.get(owner_type, owner_id, version)
        if sealed is None:
            raise NotFoundError("Secret version not found")
        try:
            return open_sealed(
                keyring(), sealed, secret_aad(owner_type, owner_id, version)
            ).decode()
        except (VaultKeyError, VaultIntegrityError) as exc:
            raise VaultError("Secret could not be decrypted", {"reason": str(exc)}) from exc

    async def next_version(self, owner_type: str, owner_id: uuid.UUID) -> int:
        return await self._repo.max_version(owner_type, owner_id) + 1

    async def shred(self, owner_type: str, owner_ids: Sequence[uuid.UUID]) -> None:
        """Delete every version of these owners' secrets."""
        await self._repo.delete_for_owners(owner_type, owner_ids)
