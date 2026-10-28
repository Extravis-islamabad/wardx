"""Append-only audit events (audit.events). A trigger refuses UPDATE and DELETE."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Row, func, select, text

from src.contracts.dto.audit.audit_event_dto import AuditEventDTO, AuditFilterDTO
from src.models import AuditEvent
from src.repositories.base import BaseRepository

_AUDIT_LOCK_KEY = 0x5741_5244_00A1


def _to_dto(row: AuditEvent) -> AuditEventDTO:
    return AuditEventDTO(
        seq=row.seq,
        id=row.id,
        occurred_at=row.occurred_at,
        actor_id=row.actor_id,
        actor_name=row.actor_name,
        action=row.action,
        object_type=row.object_type,
        object_id=row.object_id,
        outcome=row.outcome,
        source_ip=row.source_ip,
        details=row.details,
        prev_hash=row.prev_hash,
        hash=row.hash,
        key_version=row.key_version,
    )


class AuditEventRepository(BaseRepository):
    async def lock_chain(self) -> None:
        """Serialise appends until the transaction ends: each event needs the hash before it."""
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:k)"), {"k": _AUDIT_LOCK_KEY}
        )

    async def last_unkeyed_seq(self) -> int:
        """The newest legacy (pre-HMAC) event, or 0 when there are none."""
        return (
            await self._session.scalar(
                select(func.max(AuditEvent.seq)).where(AuditEvent.key_version.is_(None))
            )
        ) or 0

    async def last_hash(self) -> str | None:
        return await self._session.scalar(
            select(AuditEvent.hash).order_by(AuditEvent.seq.desc()).limit(1)
        )

    async def add(self, event: AuditEvent) -> AuditEventDTO:
        self._session.add(event)
        await self._session.flush()
        return _to_dto(event)

    async def batch_after(self, seq: int, limit: int) -> Sequence[Row]:
        # Plain rows, not entities: keeps a long chain walk out of the identity map.
        return (
            await self._session.execute(
                select(*AuditEvent.__table__.c)
                .where(AuditEvent.seq > seq)
                .order_by(AuditEvent.seq)
                .limit(limit)
            )
        ).all()

    async def list(
        self, filters: AuditFilterDTO, *, page: int, page_size: int
    ) -> tuple[list[AuditEventDTO], int]:
        conditions = []
        if filters.action:
            conditions.append(AuditEvent.action == filters.action)
        if filters.actor_id:
            conditions.append(AuditEvent.actor_id == filters.actor_id)
        if filters.object_id:
            conditions.append(AuditEvent.object_id == filters.object_id)
        if filters.since:
            conditions.append(AuditEvent.occurred_at >= filters.since)
        if filters.until:
            conditions.append(AuditEvent.occurred_at < filters.until)
        total = await self._session.scalar(
            select(func.count()).select_from(AuditEvent).where(*conditions)
        )
        rows = await self._session.scalars(
            select(AuditEvent)
            .where(*conditions)
            .order_by(AuditEvent.seq.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [_to_dto(r) for r in rows], total or 0
