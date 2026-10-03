"""Stores and reads secret versions. Callers hold the owner row lock while storing."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors.exceptions import NotFoundError, VaultError
from src.models import Secret
from src.vault.envelope import (
    Keyring,
    SealedSecret,
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


async def store(
    session: AsyncSession,
    *,
    owner_type: str,
    owner_id: uuid.UUID,
    version: int,
    plaintext: str,
    created_by: uuid.UUID | None,
) -> Secret:
    sealed = seal(keyring(), plaintext.encode(), secret_aad(owner_type, owner_id, version))
    row = Secret(
        owner_type=owner_type,
        owner_id=owner_id,
        version=version,
        ciphertext=sealed.ciphertext,
        nonce=sealed.nonce,
        wrapped_dek=sealed.wrapped_dek,
        dek_nonce=sealed.dek_nonce,
        kek_id=sealed.kek_id,
        created_by=created_by,
    )
    session.add(row)
    await session.flush()
    return row


async def read(session: AsyncSession, *, owner_type: str, owner_id: uuid.UUID, version: int) -> str:
    row = (
        await session.execute(
            select(Secret).where(
                Secret.owner_type == owner_type,
                Secret.owner_id == owner_id,
                Secret.version == version,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Secret version not found")
    sealed = SealedSecret(row.ciphertext, row.nonce, row.wrapped_dek, row.dek_nonce, row.kek_id)
    try:
        return open_sealed(keyring(), sealed, secret_aad(owner_type, owner_id, version)).decode()
    except (VaultKeyError, VaultIntegrityError) as exc:
        raise VaultError("Secret could not be decrypted", {"reason": str(exc)}) from exc
