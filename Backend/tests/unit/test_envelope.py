import base64
import dataclasses
import os
import uuid

import pytest

from src.vault.envelope import (
    Keyring,
    VaultIntegrityError,
    VaultKeyError,
    open_sealed,
    seal,
    secret_aad,
)


def _key() -> bytes:
    return os.urandom(32)


def test_round_trip():
    ring = Keyring(_key())
    aad = secret_aad("account", uuid.uuid4(), 1)
    sealed = seal(ring, b"s3cret!", aad)
    assert sealed.ciphertext != b"s3cret!"
    assert open_sealed(ring, sealed, aad) == b"s3cret!"


def test_each_seal_uses_fresh_key_and_nonce():
    ring = Keyring(_key())
    aad = secret_aad("account", uuid.uuid4(), 1)
    a, b = seal(ring, b"same", aad), seal(ring, b"same", aad)
    assert a.ciphertext != b.ciphertext
    assert a.wrapped_dek != b.wrapped_dek


def test_ciphertext_moved_to_another_owner_or_version_fails():
    ring = Keyring(_key())
    owner = uuid.uuid4()
    sealed = seal(ring, b"pw", secret_aad("account", owner, 1))
    with pytest.raises(VaultIntegrityError):
        open_sealed(ring, sealed, secret_aad("account", uuid.uuid4(), 1))
    with pytest.raises(VaultIntegrityError):
        open_sealed(ring, sealed, secret_aad("account", owner, 2))


def test_tampered_ciphertext_fails():
    ring = Keyring(_key())
    aad = secret_aad("account", uuid.uuid4(), 1)
    sealed = seal(ring, b"pw", aad)
    flipped = bytes([sealed.ciphertext[0] ^ 1]) + sealed.ciphertext[1:]
    with pytest.raises(VaultIntegrityError):
        open_sealed(ring, dataclasses.replace(sealed, ciphertext=flipped), aad)


def test_retired_key_still_opens_old_rows_and_new_seals_use_active():
    old, new = _key(), _key()
    aad = secret_aad("account", uuid.uuid4(), 1)
    sealed_old = seal(Keyring(old), b"pw", aad)
    rotated = Keyring(new, retired=[old])
    assert open_sealed(rotated, sealed_old, aad) == b"pw"
    assert seal(rotated, b"pw", aad).kek_id == rotated.active_id != sealed_old.kek_id


def test_missing_key_is_reported():
    aad = secret_aad("account", uuid.uuid4(), 1)
    sealed = seal(Keyring(_key()), b"pw", aad)
    with pytest.raises(VaultKeyError):
        open_sealed(Keyring(_key()), sealed, aad)


def test_from_base64_validates_length():
    with pytest.raises(VaultKeyError):
        Keyring.from_base64(base64.b64encode(b"short").decode())
    ring = Keyring.from_base64(base64.b64encode(_key()).decode(), "")
    assert len(ring.active_id) == 16
