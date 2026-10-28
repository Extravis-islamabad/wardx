"""Per-tenant keys: created through the key provider, stored wrapped, cached unwrapped.

A missing key is created in its own committed transaction, then read back, so
every process caches the one row that won. Creating it inside the caller's
transaction would let a rolled-back action leave a process holding a key that
no row records, and the next process would generate a different one.
"""

from __future__ import annotations

import uuid

from src.contracts.dto.keys.tenant_key_dto import TenantKeyDTO
from src.core.enums import KeyPurpose
from src.core.tenant import TenantContext
from src.errors.exceptions import VaultError
from src.keys.provider import KeyIntegrityError, KeyProvider, WrappedKey
from src.repositories.keys.tenant_key_repository import TenantKeyRepository

# (tenant_id, purpose, version) -> unwrapped key. Process memory only, never logged.
_cache: dict[tuple[uuid.UUID, str, int], bytes] = {}


def clear_cache() -> None:
    _cache.clear()


def key_aad(tenant_id: uuid.UUID, purpose: str, version: int) -> bytes:
    return f"wardx-tkek|v1|{tenant_id}|{purpose}|{version}".encode()


class TenantKeyService:
    def __init__(
        self, repo: TenantKeyRepository, provider: KeyProvider, tenant: TenantContext
    ) -> None:
        self._repo = repo
        self._provider = provider
        self._tenant = tenant

    async def active(self, purpose: KeyPurpose) -> tuple[int, bytes]:
        """The active version of the tenant's key for ``purpose``, created on first use."""
        row = await self._repo.get_active(self._tenant.tenant_id, purpose)
        if row is None:
            await self._create_first(purpose)
            row = await self._repo.get_active(self._tenant.tenant_id, purpose)
            if row is None:  # pragma: no cover - the insert above or a peer made one
                raise VaultError(f"Could not create the {purpose} key")
        return row.version, await self._unwrap(row)

    async def version(self, purpose: KeyPurpose, version: int) -> bytes | None:
        """A specific version (active or retired), or None when no such key exists."""
        cached = _cache.get((self._tenant.tenant_id, purpose, version))
        if cached is not None:
            return cached
        row = await self._repo.get_version(self._tenant.tenant_id, purpose, version)
        if row is None or row.wrapped_key is None:
            return None
        return await self._unwrap(row)

    async def _unwrap(self, row: TenantKeyDTO) -> bytes:
        ck = (row.tenant_id, row.purpose, row.version)
        if ck in _cache:
            return _cache[ck]
        try:
            key = await self._provider.unwrap(
                WrappedKey(row.kek_id, row.wrap_nonce or b"", row.wrapped_key or b""),
                key_aad(row.tenant_id, row.purpose, row.version),
            )
        except KeyIntegrityError as exc:
            raise VaultError(f"The {row.purpose} key failed authentication") from exc
        _cache[ck] = key
        return key

    async def _create_first(self, purpose: KeyPurpose) -> None:
        _, wrapped = await self._provider.generate(key_aad(self._tenant.tenant_id, purpose, 1))
        async with self._tenant.session_factory()() as own:
            await TenantKeyRepository(own).insert_first(
                tenant_id=self._tenant.tenant_id,
                purpose=purpose,
                kek_id=wrapped.key_id,
                wrapped_key=wrapped.blob,
                wrap_nonce=wrapped.nonce,
            )
            await own.commit()
