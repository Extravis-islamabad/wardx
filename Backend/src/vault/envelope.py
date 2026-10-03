"""Envelope encryption for stored secrets.

Every secret version gets a fresh 256-bit data key (DEK). The secret is sealed
with AES-256-GCM under the DEK, and the DEK is sealed under the key-encryption
key (KEK). Both seals bind associated data naming the owner and version, so a
ciphertext copied onto another account or version fails to open instead of
silently revealing the wrong secret.

The keyring holds one active KEK (new seals) and any retired KEKs (opening
older rows until they are re-wrapped). Swapping the local keyring for an HSM
(PKCS#11) or cloud KMS only changes how ``wrap``/``unwrap`` reach the KEK.
"""

from __future__ import annotations

import base64
import hashlib
import os
from collections.abc import Iterable
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_BYTES = 12
_KEY_BYTES = 32
_DEK_AAD_PREFIX = b"wardx-dek|"


class VaultKeyError(Exception):
    """A KEK is missing or malformed."""


class VaultIntegrityError(Exception):
    """Ciphertext failed authentication: wrong key, wrong owner, or tampered data."""


@dataclass(frozen=True)
class SealedSecret:
    ciphertext: bytes
    nonce: bytes
    wrapped_dek: bytes
    dek_nonce: bytes
    kek_id: str


def key_id(key: bytes) -> str:
    return hashlib.sha256(b"wardx-kek-id|" + key).hexdigest()[:16]


def decode_key(b64: str) -> bytes:
    try:
        key = base64.b64decode(b64.strip(), validate=True)
    except ValueError as exc:
        raise VaultKeyError("KEK is not valid base64") from exc
    if len(key) != _KEY_BYTES:
        raise VaultKeyError(f"KEK must be {_KEY_BYTES} bytes, got {len(key)}")
    return key


class Keyring:
    def __init__(self, active: bytes, retired: Iterable[bytes] = ()) -> None:
        self._keys = {key_id(k): k for k in retired}
        self.active_id = key_id(active)
        self._keys[self.active_id] = active

    @classmethod
    def from_base64(cls, active: str, retired: str = "") -> Keyring:
        return cls(decode_key(active), [decode_key(k) for k in retired.split(",") if k.strip()])

    def get(self, kek_id: str) -> bytes:
        try:
            return self._keys[kek_id]
        except KeyError as exc:
            raise VaultKeyError(f"KEK {kek_id} is not loaded") from exc

    def wrap(self, dek: bytes, aad: bytes) -> tuple[str, bytes, bytes]:
        nonce = os.urandom(_NONCE_BYTES)
        wrapped = AESGCM(self.get(self.active_id)).encrypt(nonce, dek, _DEK_AAD_PREFIX + aad)
        return self.active_id, nonce, wrapped

    def unwrap(self, kek_id: str, nonce: bytes, wrapped: bytes, aad: bytes) -> bytes:
        try:
            return AESGCM(self.get(kek_id)).decrypt(nonce, wrapped, _DEK_AAD_PREFIX + aad)
        except InvalidTag as exc:
            raise VaultIntegrityError("data key failed authentication") from exc


def secret_aad(owner_type: str, owner_id: object, version: int) -> bytes:
    return f"{owner_type}:{owner_id}:{version}".encode()


def seal(keyring: Keyring, plaintext: bytes, aad: bytes) -> SealedSecret:
    dek = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(dek).encrypt(nonce, plaintext, aad)
    kek_id, dek_nonce, wrapped = keyring.wrap(dek, aad)
    return SealedSecret(ciphertext, nonce, wrapped, dek_nonce, kek_id)


def open_sealed(keyring: Keyring, sealed: SealedSecret, aad: bytes) -> bytes:
    dek = keyring.unwrap(sealed.kek_id, sealed.dek_nonce, sealed.wrapped_dek, aad)
    try:
        return AESGCM(dek).decrypt(sealed.nonce, sealed.ciphertext, aad)
    except InvalidTag as exc:
        raise VaultIntegrityError("secret failed authentication") from exc
