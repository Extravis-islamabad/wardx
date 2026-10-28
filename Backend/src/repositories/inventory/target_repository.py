"""Targets (inventory.targets)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from src.contracts.dto.inventory.target_dto import TargetDTO, TargetFilterDTO
from src.errors.exceptions import ConflictError
from src.models import Target
from src.repositories.base import BaseRepository


def _to_dto(row: Target) -> TargetDTO:
    return TargetDTO(
        id=row.id,
        name=row.name,
        address=row.address,
        platform=row.platform,
        protocol=row.protocol,
        port=row.port,
        description=row.description,
        tags=list(row.tags or []),
        external_ref=row.external_ref,
        is_active=row.is_active,
        ssh_host_key=row.ssh_host_key,
        ssh_host_key_fingerprint=row.ssh_host_key_fingerprint,
        ssh_host_key_learned_at=row.ssh_host_key_learned_at,
        host_key_mismatch_at=row.host_key_mismatch_at,
        host_key_mismatch_fingerprint=row.host_key_mismatch_fingerprint,
        api_port=row.api_port,
        api_tls=row.api_tls,
        tls_cert_pem=row.tls_cert_pem,
        tls_cert_fingerprint=row.tls_cert_fingerprint,
        tls_cert_learned_at=row.tls_cert_learned_at,
        tls_cert_mismatch_at=row.tls_cert_mismatch_at,
        tls_cert_mismatch_fingerprint=row.tls_cert_mismatch_fingerprint,
        created_at=row.created_at,
        updated_at=row.updated_at,
        rotation_allowed=row.rotation_allowed,
        policy_overrides=dict(row.policy_overrides or {}),
    )


class TargetRepository(BaseRepository):
    async def list(
        self, filters: TargetFilterDTO, *, page: int, page_size: int
    ) -> tuple[list[TargetDTO], int]:
        conditions = []
        if filters.search:
            like = f"%{filters.search.lower()}%"
            conditions.append(
                or_(func.lower(Target.name).like(like), func.lower(Target.address).like(like))
            )
        if filters.platform:
            conditions.append(Target.platform == filters.platform)
        total = await self._session.scalar(
            select(func.count()).select_from(Target).where(*conditions)
        )
        rows = await self._session.scalars(
            select(Target)
            .where(*conditions)
            .order_by(func.lower(Target.name))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [_to_dto(r) for r in rows], total or 0

    async def get(self, target_id: uuid.UUID, *, lock: bool = False) -> TargetDTO | None:
        row = await self._session.get(Target, target_id, with_for_update=lock or None)
        return _to_dto(row) if row else None

    async def find_by_name(self, name: str) -> TargetDTO | None:
        """The target with this name, ignoring case."""
        row = (
            await self._session.execute(
                select(Target).where(func.lower(Target.name) == name.lower())
            )
        ).scalar_one_or_none()
        return _to_dto(row) if row else None

    async def pin_host_key(
        self, target_id: uuid.UUID, *, key: str, fingerprint: str, learned_at: datetime
    ) -> bool:
        """Store a first-seen host key; False if the target already has one pinned."""
        result = await self._session.execute(
            update(Target)
            .where(Target.id == target_id, Target.ssh_host_key.is_(None))
            .values(
                ssh_host_key=key,
                ssh_host_key_fingerprint=fingerprint,
                ssh_host_key_learned_at=learned_at,
            )
        )
        return result.rowcount > 0

    async def accept_host_key(
        self, target_id: uuid.UUID, *, key: str, fingerprint: str, learned_at: datetime
    ) -> None:
        """Pin (or re-pin) the key an administrator accepted, and clear any mismatch."""
        await self._session.execute(
            update(Target)
            .where(Target.id == target_id)
            .values(
                ssh_host_key=key,
                ssh_host_key_fingerprint=fingerprint,
                ssh_host_key_learned_at=learned_at,
                host_key_mismatch_at=None,
                host_key_mismatch_fingerprint=None,
            )
        )

    async def record_host_key_mismatch(
        self, target_id: uuid.UUID, *, presented: str | None, seen_at: datetime
    ) -> bool:
        """Mark the target as presenting an unpinned key. True when this is a new mismatch
        (none recorded yet, or a different presented fingerprint), so callers alert once
        per new key rather than once per attempt."""
        row = await self._session.get(Target, target_id, with_for_update=True)
        if row is None:
            return False
        new = row.host_key_mismatch_at is None or (row.host_key_mismatch_fingerprint != presented)
        if new:
            row.host_key_mismatch_at = seen_at
            row.host_key_mismatch_fingerprint = presented
            await self._session.flush()
        return new

    async def accept_tls_cert(
        self, target_id: uuid.UUID, *, pem: str, fingerprint: str, learned_at: datetime
    ) -> None:
        """Pin (or re-pin) the API-SSL certificate an administrator accepted, and clear
        any recorded certificate mismatch."""
        await self._session.execute(
            update(Target)
            .where(Target.id == target_id)
            .values(
                tls_cert_pem=pem,
                tls_cert_fingerprint=fingerprint,
                tls_cert_learned_at=learned_at,
                tls_cert_mismatch_at=None,
                tls_cert_mismatch_fingerprint=None,
            )
        )

    async def record_tls_cert_mismatch(
        self, target_id: uuid.UUID, *, presented: str | None, seen_at: datetime
    ) -> bool:
        """Mark the target as presenting an unpinned certificate. True when this is a new
        mismatch (none recorded yet, or another presented fingerprint)."""
        row = await self._session.get(Target, target_id, with_for_update=True)
        if row is None:
            return False
        new = row.tls_cert_mismatch_at is None or row.tls_cert_mismatch_fingerprint != presented
        if new:
            row.tls_cert_mismatch_at = seen_at
            row.tls_cert_mismatch_fingerprint = presented
            await self._session.flush()
        return new

    async def create(self, values: dict[str, Any]) -> TargetDTO:
        row = Target(**values)
        self._session.add(row)
        await self._flush_unique()
        return _to_dto(row)

    async def update(self, target_id: uuid.UUID, changes: dict[str, Any]) -> TargetDTO | None:
        row = await self._session.get(Target, target_id)
        if row is None:
            return None
        for field, value in changes.items():
            setattr(row, field, value)
        await self._flush_unique()
        return _to_dto(row)

    async def delete(self, target_id: uuid.UUID) -> None:
        row = await self._session.get(Target, target_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    async def _flush_unique(self) -> None:
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("A target with this name already exists") from exc
