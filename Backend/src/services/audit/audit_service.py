"""Writes, lists and verifies the hash-chained audit trail.

``record`` runs inside the caller's transaction, so an action and its audit
event commit or roll back together.
"""

from __future__ import annotations

import uuid
from typing import Any

from src.contracts.dto.audit.audit_event_dto import AuditEventDTO, AuditFilterDTO
from src.core.context import Actor
from src.models import AuditEvent, utcnow
from src.repositories.audit.audit_event_repository import AuditEventRepository
from src.services.audit.audit_chain import (
    GENESIS_HASH,
    ChainCheck,
    canonical,
    chain_hash,
    verify_events,
)

_VERIFY_BATCH = 2000


class AuditService:
    def __init__(self, repo: AuditEventRepository) -> None:
        self._repo = repo

    async def record(
        self,
        actor: Actor,
        action: str,
        *,
        object_type: str | None = None,
        object_id: uuid.UUID | None = None,
        outcome: str = "success",
        details: dict[str, Any] | None = None,
    ) -> AuditEventDTO:
        await self._repo.lock_chain()
        prev = await self._repo.last_hash() or GENESIS_HASH
        event_id = uuid.uuid4()
        occurred_at = utcnow()
        details = details or {}
        body = canonical(
            event_id=event_id,
            occurred_at=occurred_at,
            actor_id=actor.id,
            actor_name=actor.username,
            action=action,
            object_type=object_type,
            object_id=object_id,
            outcome=outcome,
            source_ip=actor.source_ip,
            details=details,
        )
        return await self._repo.add(
            AuditEvent(
                id=event_id,
                occurred_at=occurred_at,
                actor_id=actor.id,
                actor_name=actor.username,
                action=action,
                object_type=object_type,
                object_id=object_id,
                outcome=outcome,
                source_ip=actor.source_ip,
                details=details,
                prev_hash=prev,
                hash=chain_hash(prev, body),
            )
        )

    async def verify_chain(self) -> ChainCheck:
        """Walk the whole chain in batches of ``_VERIFY_BATCH`` events."""
        prev, total, after = GENESIS_HASH, 0, 0
        while True:
            rows = await self._repo.batch_after(after, _VERIFY_BATCH)
            if not rows:
                return ChainCheck(True, total, prev)
            result = verify_events(rows, prev)
            total += result.checked
            if not result.ok:
                return ChainCheck(
                    False, total, result.last_hash, result.broken_at_seq, result.reason
                )
            prev, after = result.last_hash, rows[-1].seq

    async def list_events(
        self, filters: AuditFilterDTO, *, page: int, page_size: int
    ) -> tuple[list[AuditEventDTO], int]:
        return await self._repo.list(filters, page=page, page_size=page_size)
