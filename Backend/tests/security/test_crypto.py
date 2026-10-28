"""Vault crypto: AES-256-GCM envelope round-trips, and refuses wrong keys and any tampering.

Complements tests/unit/test_envelope.py. Every refusal must be an exception;
none may return bytes, wrong or otherwise.
"""

from __future__ import annotations

import dataclasses
import os
import uuid

import pytest
from sqlalchemy import text

from src.core.db import session_factory
from src.keys.file_provider import FileKeyProvider
from src.vault.envelope import (
    SealedSecret,
    VaultIntegrityError,
    VaultKeyError,
    open_sealed,
    seal,
    secret_aad,
)

AAD = secret_aad("account", uuid.UUID(int=1), 1)


async def _sealed(plaintext: bytes = b"S3cret-value") -> tuple[FileKeyProvider, SealedSecret]:
    ring = FileKeyProvider(os.urandom(32))
    return ring, await seal(ring, plaintext, AAD)


def _flip(data: bytes, index: int = 0) -> bytes:
    return data[:index] + bytes([data[index] ^ 0x01]) + data[index + 1 :]


@pytest.mark.parametrize("plaintext", [b"", b"x", b"p@ss w0rd \xe2\x9c\x93", os.urandom(4096)])
async def test_round_trip(plaintext):
    ring, sealed = await _sealed(plaintext)
    assert await open_sealed(ring, sealed, AAD) == plaintext


async def test_authenticated_mode_shape():
    # AES-GCM: 96-bit nonces and a 128-bit tag on both layers; the plaintext is not in the output.
    ring, sealed = await _sealed(b"S3cret-value")
    assert len(sealed.nonce) == 12 and len(sealed.dek_nonce) == 12
    assert len(sealed.ciphertext) == len(b"S3cret-value") + 16
    assert len(sealed.wrapped_dek) == 32 + 16
    assert b"S3cret-value" not in sealed.ciphertext


async def test_unknown_key_is_refused():
    _, sealed = await _sealed()
    with pytest.raises(VaultKeyError):
        await open_sealed(FileKeyProvider(os.urandom(32)), sealed, AAD)


async def test_wrong_key_under_the_right_id_fails_authentication():
    # Even if a different key were loaded under the expected id, GCM's tag rejects it.
    _, sealed = await _sealed()
    impostor = FileKeyProvider(os.urandom(32))
    impostor._keys[sealed.kek_id] = os.urandom(32)
    with pytest.raises(VaultIntegrityError):
        await open_sealed(impostor, sealed, AAD)


@pytest.mark.parametrize("field", ["ciphertext", "nonce", "wrapped_dek", "dek_nonce"])
@pytest.mark.parametrize("where", ["first", "last"])
async def test_any_tampered_byte_is_detected(field, where):
    ring, sealed = await _sealed()
    value = getattr(sealed, field)
    tampered = dataclasses.replace(sealed, **{field: _flip(value, 0 if where == "first" else -1)})
    with pytest.raises(VaultIntegrityError):
        await open_sealed(ring, tampered, AAD)


@pytest.mark.parametrize("field", ["ciphertext", "wrapped_dek"])
async def test_truncated_data_is_detected(field):
    ring, sealed = await _sealed()
    tampered = dataclasses.replace(sealed, **{field: getattr(sealed, field)[:-1]})
    with pytest.raises(VaultIntegrityError):
        await open_sealed(ring, tampered, AAD)


async def test_swapped_data_key_is_detected():
    # A data key lifted from another secret cannot open this one.
    ring, sealed = await _sealed()
    other = await seal(ring, b"other", secret_aad("account", uuid.UUID(int=2), 1))
    swapped = dataclasses.replace(sealed, wrapped_dek=other.wrapped_dek, dek_nonce=other.dek_nonce)
    with pytest.raises(VaultIntegrityError):
        await open_sealed(ring, swapped, AAD)


async def test_tampered_row_in_database_is_refused_not_revealed(client, admin, make_user):
    """End to end: a ciphertext edited in vault.secrets yields vault_error, never a value."""
    target = (
        await client.post(
            "/targets",
            headers=admin,
            json={
                "name": "crypto-t1",
                "address": "10.9.9.9",
                "platform": "linux",
                "protocol": "ssh",
            },
        )
    ).json()["data"]
    account = (
        await client.post(
            "/accounts",
            headers=admin,
            json={"target_id": target["id"], "username": "root", "secret": "Orig-Secret-1"},
        )
    ).json()["data"]
    user = await make_user("cryptouser1")
    co = (
        await client.post(
            "/checkouts", headers=user, json={"account_id": account["id"], "reason": "crypto test"}
        )
    ).json()["data"]

    async with session_factory()() as session:
        await session.execute(
            text(
                "UPDATE vault.secrets SET ciphertext = set_byte(ciphertext, 0, "
                "get_byte(ciphertext, 0) # 1) WHERE owner_id = :id"
            ),
            {"id": account["id"]},
        )
        await session.commit()

    resp = await client.post(f"/checkouts/{co['id']}/reveal", headers=user)
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "vault_error"
    assert "Orig-Secret-1" not in resp.text
