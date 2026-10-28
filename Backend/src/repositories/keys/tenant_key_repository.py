"""Wrapped tenant keys (keystore.tenant_keys). A trigger forbids deletes and edits."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from src.contracts.dto.keys.tenant_key_dto import TenantKeyDTO
from src.models import TenantKey
from src.repositories.base import BaseRepository


def _to_dto(row: TenantKey) -> TenantKeyDTO:
    return TenantKeyDTO(
        id=row.id,
        tenant_id=row.tenant_id,
        purpose=row.purpose,
        version=row.version,
        state=row.state,
        kek_id=row.kek_id,
        wrapped_key=row.wrapped_key,
        wrap_nonce=row.wrap_nonce,
    )


class TenantKeyRepository(BaseRepository):
    async def get_active(self, tenant_id: uuid.UUID, purpose: str) -> TenantKeyDTO | None:
        row = await self._session.scalar(
            select(TenantKey).where(
                TenantKey.tenant_id == tenant_id,
                TenantKey.purpose == purpose,
                TenantKey.state == "active",
            )
        )
        return _to_dto(row) if row else None

    async def get_version(
        self, tenant_id: uuid.UUID, purpose: str, version: int
    ) -> TenantKeyDTO | None:
        row = await self._session.scalar(
            select(TenantKey).where(
                TenantKey.tenant_id == tenant_id,
                TenantKey.purpose == purpose,
                TenantKey.version == version,
            )
        )
        return _to_dto(row) if row else None

    async def insert_first(
        self,
        *,
        tenant_id: uuid.UUID,
        purpose: str,
        kek_id: str,
        wrapped_key: bytes,
        wrap_nonce: bytes,
    ) -> None:
        """Insert version 1 as active unless another process already did."""
        await self._session.execute(
            insert(TenantKey)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                purpose=purpose,
                version=1,
                state="active",
                kek_id=kek_id,
                wrapped_key=wrapped_key,
                wrap_nonce=wrap_nonce,
            )
            .on_conflict_do_nothing()
        )
