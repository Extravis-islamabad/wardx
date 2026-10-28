"""The process-wide key provider, loaded once at startup.

Until ``set_key_provider`` runs the vault is sealed: every seal, open and
tenant-key lookup fails closed.
"""

from __future__ import annotations

from src.errors.exceptions import VaultError
from src.keys.provider import KeyProvider

_provider: KeyProvider | None = None


def set_key_provider(provider: KeyProvider | None) -> None:
    global _provider
    _provider = provider


def key_provider() -> KeyProvider:
    if _provider is None:
        raise VaultError("Vault is sealed: no key provider loaded")
    return _provider
