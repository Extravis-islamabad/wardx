"""Key provider backed by key-encryption keys from config or a dev file.

Development and test only in the long run (TENANCY_KEYS.md §4): the KEKs are
plain bytes in this process. Wraps with AES-256-GCM; the format is the one the
vault has always used, so secrets sealed before this provider still open.
"""

from __future__ import annotations

import base64
import hashlib
import os
from collections.abc import Iterable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.keys.provider import KeyIntegrityError, KeyProviderError, WrappedKey

_NONCE_BYTES = 12
_KEY_BYTES = 32


def key_id(key: bytes) -> str:
    return hashlib.sha256(b"wardx-kek-id|" + key).hexdigest()[:16]


def decode_key(b64: str) -> bytes:
    try:
        key = base64.b64decode(b64.strip(), validate=True)
    except ValueError as exc:
        raise KeyProviderError("KEK is not valid base64") from exc
    if len(key) != _KEY_BYTES:
        raise KeyProviderError(f"KEK must be {_KEY_BYTES} bytes, got {len(key)}")
    return key


class FileKeyProvider:
    """One active KEK for new wraps, plus retired KEKs that still unwrap."""

    def __init__(self, active: bytes, retired: Iterable[bytes] = ()) -> None:
        self._keys = {key_id(k): k for k in retired}
        self._active_id = key_id(active)
        self._keys[self._active_id] = active

    @classmethod
    def from_base64(cls, active: str, retired: str = "") -> FileKeyProvider:
        return cls(decode_key(active), [decode_key(k) for k in retired.split(",") if k.strip()])

    @property
    def active_key_id(self) -> str:
        return self._active_id

    def _kek(self, kid: str) -> bytes:
        try:
            return self._keys[kid]
        except KeyError as exc:
            raise KeyProviderError(f"KEK {kid} is not loaded") from exc

    async def wrap(self, key: bytes, aad: bytes) -> WrappedKey:
        nonce = os.urandom(_NONCE_BYTES)
        blob = AESGCM(self._kek(self._active_id)).encrypt(nonce, key, aad)
        return WrappedKey(self._active_id, nonce, blob)

    async def unwrap(self, wrapped: WrappedKey, aad: bytes) -> bytes:
        try:
            return AESGCM(self._kek(wrapped.key_id)).decrypt(wrapped.nonce, wrapped.blob, aad)
        except InvalidTag as exc:
            raise KeyIntegrityError("wrapped key failed authentication") from exc

    async def generate(self, aad: bytes) -> tuple[bytes, WrappedKey]:
        key = AESGCM.generate_key(bit_length=256)
        return key, await self.wrap(key, aad)

    async def health(self) -> str:
        return "available"
