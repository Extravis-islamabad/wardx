"""Writes, lists and verifies the keyed, hash-chained audit trail.

``record`` runs inside the caller's transaction, so an action and its audit
event commit or roll back together. Each event is HMAC'd with the tenant's
audit key (see audit_chain.py for the chain rules).
"""

from __future__ import annotations

import uuid
from typing import Any

from src.contracts.dto.audit.audit_event_dto import AuditEventDTO, AuditFilterDTO
from src.core.context import Actor
from src.core.enums import KeyPurpose
from src.models import AuditEvent, utcnow
from src.repositories.audit.audit_event_repository import AuditEventRepository
from src.services.audit.audit_chain import (
    GENESIS_HASH,
    ChainCheck,
    canonical,
    chain_hash,
    verify_events,
)
from src.services.keys.tenant_key_service import TenantKeyService

_VERIFY_BATCH = 2000


class AuditService:
    def __init__(
        self, repo: AuditEventRepository, keys: TenantKeyService, *, legacy_max_seq: int = 0
    ) -> None:
        self._repo = repo
        self._tenant_keys = keys
        # Last seq allowed to be an unkeyed legacy event; pinned outside the database.
        self._legacy_max_seq = legacy_max_seq

    async def record(
        self,
        actor: Actor,
        action: str,
        *,
        object_type: str | None = None,
        object_id: uuid.UUID | None = None,
        outcome: str = "success",
        details: dict[str, Any] | None = None,
        safe_id: uuid.UUID | None = None,
    ) -> AuditEventDTO:
        details = details or {}
        if safe_id is None:
            safe_id = await self._resolve_safe(object_type, object_id, details)
        key_version, key = await self._tenant_keys.active(KeyPurpose.AUDIT)
        await self._repo.lock_chain()
        prev = await self._repo.last_hash() or GENESIS_HASH
        event_id = uuid.uuid4()
        occurred_at = utcnow()
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
            key_version=key_version,
            safe_id=safe_id,
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
                hash=chain_hash(prev, body, key),
                key_version=key_version,
                safe_id=safe_id,
            )
        )

    async def _resolve_safe(
        self, object_type: str | None, object_id: uuid.UUID | None, details: dict[str, Any]
    ) -> uuid.UUID | None:
        """The safe an event belongs to when the caller did not name one: the current safe
        of its account, request, check-out or session, or of one referenced in the
        details (e.g. a host-key event's session). Resolved at write time, so the event
        keeps the safe it happened in. Callers pass ``safe_id`` explicitly where the
        lookup would be wrong (an account move, a deleted account)."""
        candidates: list[tuple[str, Any]] = []
        if object_type and object_id:
            candidates.append((object_type, object_id))
        for kind in ("session", "checkout", "request", "account"):
            if details.get(f"{kind}_id"):
                candidates.append((kind, details[f"{kind}_id"]))
        for kind, ref in candidates:
            try:
                ref_id = ref if isinstance(ref, uuid.UUID) else uuid.UUID(str(ref))
            except ValueError:
                continue
            found = await self._repo.safe_of(kind, ref_id)
            if found is not None:
                return found
        return None

    async def verify_chain(self) -> ChainCheck:
        """Walk the whole chain in batches of ``_VERIFY_BATCH`` events."""
        prev, total, after, keyed_seen = GENESIS_HASH, 0, 0, False
        keys: dict[int, bytes] = {}
        while True:
            rows = await self._repo.batch_after(after, _VERIFY_BATCH)
            if not rows:
                return ChainCheck(True, total, prev)
            for v in {r.key_version for r in rows if r.key_version is not None} - keys.keys():
                key = await self._tenant_keys.version(KeyPurpose.AUDIT, v)
                if key is not None:
                    keys[v] = key
            result = verify_events(
                rows,
                prev,
                keys=keys,
                legacy_max_seq=self._legacy_max_seq,
                keyed_seen=keyed_seen,
            )
            total += result.checked
            if not result.ok:
                return ChainCheck(
                    False, total, result.last_hash, result.broken_at_seq, result.reason
                )
            prev, after, keyed_seen = result.last_hash, rows[-1].seq, result.keyed_seen

    async def list_events(
        self, filters: AuditFilterDTO, *, page: int, page_size: int
    ) -> tuple[list[AuditEventDTO], int]:
        return await self._repo.list(filters, page=page, page_size=page_size)
