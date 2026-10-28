import base64
import dataclasses
import os
import uuid

import pytest

from src.keys.file_provider import FileKeyProvider
from src.vault.envelope import (
    VaultIntegrityError,
    VaultKeyError,
    open_sealed,
    seal,
    secret_aad,
)


def _key() -> bytes:
    return os.urandom(32)


async def test_round_trip():
    ring = FileKeyProvider(_key())
    aad = secret_aad("account", uuid.uuid4(), 1)
    sealed = await seal(ring, b"s3cret!", aad)
    assert sealed.ciphertext != b"s3cret!"
    assert await open_sealed(ring, sealed, aad) == b"s3cret!"


async def test_each_seal_uses_fresh_key_and_nonce():
    ring = FileKeyProvider(_key())
    aad = secret_aad("account", uuid.uuid4(), 1)
    a, b = await seal(ring, b"same", aad), await seal(ring, b"same", aad)
    assert a.ciphertext != b.ciphertext
    assert a.wrapped_dek != b.wrapped_dek


async def test_ciphertext_moved_to_another_owner_or_version_fails():
    ring = FileKeyProvider(_key())
    owner = uuid.uuid4()
    sealed = await seal(ring, b"pw", secret_aad("account", owner, 1))
    with pytest.raises(VaultIntegrityError):
        await open_sealed(ring, sealed, secret_aad("account", uuid.uuid4(), 1))
    with pytest.raises(VaultIntegrityError):
        await open_sealed(ring, sealed, secret_aad("account", owner, 2))


async def test_tampered_ciphertext_fails():
    ring = FileKeyProvider(_key())
    aad = secret_aad("account", uuid.uuid4(), 1)
    sealed = await seal(ring, b"pw", aad)
    flipped = bytes([sealed.ciphertext[0] ^ 1]) + sealed.ciphertext[1:]
    with pytest.raises(VaultIntegrityError):
        await open_sealed(ring, dataclasses.replace(sealed, ciphertext=flipped), aad)


async def test_retired_key_still_opens_old_rows_and_new_seals_use_active():
    old, new = _key(), _key()
    aad = secret_aad("account", uuid.uuid4(), 1)
    sealed_old = await seal(FileKeyProvider(old), b"pw", aad)
    rotated = FileKeyProvider(new, retired=[old])
    assert await open_sealed(rotated, sealed_old, aad) == b"pw"
    assert (await seal(rotated, b"pw", aad)).kek_id == rotated.active_key_id != sealed_old.kek_id


async def test_missing_key_is_reported():
    aad = secret_aad("account", uuid.uuid4(), 1)
    sealed = await seal(FileKeyProvider(_key()), b"pw", aad)
    with pytest.raises(VaultKeyError):
        await open_sealed(FileKeyProvider(_key()), sealed, aad)


async def test_from_base64_validates_length():
    with pytest.raises(VaultKeyError):
        FileKeyProvider.from_base64(base64.b64encode(b"short").decode())
    ring = FileKeyProvider.from_base64(base64.b64encode(_key()).decode(), "")
    assert len(ring.active_key_id) == 16
