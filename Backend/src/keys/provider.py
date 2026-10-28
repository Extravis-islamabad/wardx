"""The master-key provider interface (Backend/TENANCY_KEYS.md §4).

A provider wraps and unwraps keys under a key-encryption key it holds. Callers
pass the associated data; a wrapped key only unwraps with the same AAD, so a
blob moved to another owner or purpose fails instead of opening.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class KeyProviderError(Exception):
    """A key-encryption key is missing, malformed, or the provider is unreachable."""


class KeyIntegrityError(Exception):
    """A wrapped key failed authentication: wrong key, wrong AAD, or tampered bytes."""


@dataclass(frozen=True)
class WrappedKey:
    key_id: str  # which key-encryption key wrapped it
    nonce: bytes
    blob: bytes


class KeyProvider(Protocol):
    @property
    def active_key_id(self) -> str: ...

    async def wrap(self, key: bytes, aad: bytes) -> WrappedKey: ...

    async def unwrap(self, wrapped: WrappedKey, aad: bytes) -> bytes:
        """Unwrap under any key the provider still holds (active or retired)."""
        ...

    async def generate(self, aad: bytes) -> tuple[bytes, WrappedKey]:
        """A new 256-bit key and its wrapped form (in-HSM where the provider can)."""
        ...

    async def health(self) -> str:
        """'available', or raises KeyProviderError."""
        ...
