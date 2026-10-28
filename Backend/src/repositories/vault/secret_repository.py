"""Sealed secret versions in vault.secrets. Never sees plaintext."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select, update

from src.models import Secret
from src.repositories.base import BaseRepository
from src.vault.envelope import SealedSecret


class SecretRepository(BaseRepository):
    async def add(
        self,
        *,
        owner_type: str,
        owner_id: uuid.UUID,
        version: int,
        sealed: SealedSecret,
        created_by: uuid.UUID | None,
        status: str | None = None,
    ) -> None:
        self._session.add(
            Secret(
                owner_type=owner_type,
                owner_id=owner_id,
                version=version,
                ciphertext=sealed.ciphertext,
                nonce=sealed.nonce,
                wrapped_dek=sealed.wrapped_dek,
                dek_nonce=sealed.dek_nonce,
                kek_id=sealed.kek_id,
                created_by=created_by,
                status=status,
            )
        )
        await self._session.flush()

    async def set_status(
        self, owner_type: str, owner_id: uuid.UUID, version: int, status: str
    ) -> None:
        await self._session.execute(
            update(Secret)
            .where(
                Secret.owner_type == owner_type,
                Secret.owner_id == owner_id,
                Secret.version == version,
            )
            .values(status=status)
        )

    async def demote_current(self, owner_type: str, owner_id: uuid.UUID) -> None:
        """Relabel the current version 'previous' (the caller labels the new current)."""
        await self._session.execute(
            update(Secret)
            .where(
                Secret.owner_type == owner_type,
                Secret.owner_id == owner_id,
                Secret.status == "current",
            )
            .values(status="previous")
        )

    async def statuses(self, owner_type: str, owner_id: uuid.UUID) -> dict[int, str | None]:
        rows = await self._session.execute(
            select(Secret.version, Secret.status).where(
                Secret.owner_type == owner_type, Secret.owner_id == owner_id
            )
        )
        return dict(rows.all())

    async def get(self, owner_type: str, owner_id: uuid.UUID, version: int) -> SealedSecret | None:
        row = await self._session.scalar(
            select(Secret).where(
                Secret.owner_type == owner_type,
                Secret.owner_id == owner_id,
                Secret.version == version,
            )
        )
        if row is None:
            return None
        return SealedSecret(row.ciphertext, row.nonce, row.wrapped_dek, row.dek_nonce, row.kek_id)

    async def max_version(self, owner_type: str, owner_id: uuid.UUID) -> int:
        current = await self._session.scalar(
            select(func.max(Secret.version)).where(
                Secret.owner_type == owner_type, Secret.owner_id == owner_id
            )
        )
        return current or 0

    async def delete_for_owners(self, owner_type: str, owner_ids: Sequence[uuid.UUID]) -> None:
        if owner_ids:
            await self._session.execute(
                delete(Secret).where(
                    Secret.owner_type == owner_type, Secret.owner_id.in_(owner_ids)
                )
            )
