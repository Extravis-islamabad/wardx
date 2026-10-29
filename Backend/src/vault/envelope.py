"""Envelope encryption for stored secrets.

Every secret version gets a fresh 256-bit data key (DEK). The secret is sealed
with AES-256-GCM under the DEK, and the DEK is wrapped by the key provider
(src/keys). Both seals bind associated data naming the owner and version, so a
ciphertext copied onto another account or version fails to open instead of
silently revealing the wrong secret.

This module never sees a key-encryption key: wrapping and unwrapping happen
inside the provider, which is how an HSM or KMS slots in later.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.keys.provider import KeyIntegrityError, KeyProvider, KeyProviderError, WrappedKey

_NONCE_BYTES = 12
_DEK_AAD_PREFIX = b"wardx-dek|"

# A key-encryption key is missing or malformed, or the provider is unreachable.
VaultKeyError = KeyProviderError


class VaultIntegrityError(Exception):
    """Ciphertext failed authentication: wrong key, wrong owner, or tampered data."""


@dataclass(frozen=True)
class SealedSecret:
    ciphertext: bytes
    nonce: bytes
    wrapped_dek: bytes
    dek_nonce: bytes
    kek_id: str


def secret_aad(owner_type: str, owner_id: object, version: int) -> bytes:
    return f"{owner_type}:{owner_id}:{version}".encode()


async def seal(provider: KeyProvider, plaintext: bytes, aad: bytes) -> SealedSecret:
    dek = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(dek).encrypt(nonce, plaintext, aad)
    wrapped = await provider.wrap(dek, _DEK_AAD_PREFIX + aad)
    return SealedSecret(ciphertext, nonce, wrapped.blob, wrapped.nonce, wrapped.key_id)


async def open_sealed(provider: KeyProvider, sealed: SealedSecret, aad: bytes) -> bytes:
    try:
        dek = await provider.unwrap(
            WrappedKey(sealed.kek_id, sealed.dek_nonce, sealed.wrapped_dek), _DEK_AAD_PREFIX + aad
        )
    except KeyIntegrityError as exc:
        raise VaultIntegrityError("data key failed authentication") from exc
    try:
        return AESGCM(dek).decrypt(sealed.nonce, sealed.ciphertext, aad)
    except InvalidTag as exc:
        raise VaultIntegrityError("secret failed authentication") from exc


# ── Streaming data encryption (session recordings, HA_DR.md §5.1) ──
# Data keys only: the caller passes a per-object DEK, or a tenant purpose key from
# TenantKeyService to wrap that DEK. Key-encryption keys never reach this module.

DATA_KEY_BYTES = 32
GCM_TAG_BYTES = 16


def new_data_key() -> bytes:
    return AESGCM.generate_key(bit_length=DATA_KEY_BYTES * 8)


def aead_seal(key: bytes, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes:
    """AES-256-GCM: ciphertext with its 16-byte tag appended."""
    return AESGCM(key).encrypt(nonce, plaintext, aad)


def aead_open(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise VaultIntegrityError("data failed authentication") from exc


def wrap_data_key(purpose_key: bytes, dek: bytes, aad: bytes) -> tuple[bytes, bytes]:
    """Wrap a DEK under a tenant purpose key; returns (nonce, wrapped)."""
    nonce = os.urandom(_NONCE_BYTES)
    return nonce, aead_seal(purpose_key, nonce, dek, _DEK_AAD_PREFIX + aad)


def unwrap_data_key(purpose_key: bytes, nonce: bytes, wrapped: bytes, aad: bytes) -> bytes:
    return aead_open(purpose_key, nonce, wrapped, _DEK_AAD_PREFIX + aad)
