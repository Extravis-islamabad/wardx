"""Writes and reads the audit trail.

``record`` runs inside the caller's transaction, so an action and its audit
event commit or roll back together. Appends are serialised by a transaction
advisory lock: the chain needs each event to see the hash written before it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.context import Actor
from src.models import AuditEvent, utcnow
from src.services.audit_chain import GENESIS_HASH, ChainCheck, canonical, chain_hash, verify_events

_AUDIT_LOCK_KEY = 0x5741_5244_00A1
_VERIFY_BATCH = 2000


async def record(
    session: AsyncSession,
    actor: Actor,
    action: str,
    *,
    object_type: str | None = None,
    object_id: uuid.UUID | None = None,
    outcome: str = "success",
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _AUDIT_LOCK_KEY})
    prev = (
        await session.execute(select(AuditEvent.hash).order_by(AuditEvent.seq.desc()).limit(1))
    ).scalar_one_or_none() or GENESIS_HASH

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
    event = AuditEvent(
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
    session.add(event)
    await session.flush()
    return event


async def verify_chain(session: AsyncSession) -> ChainCheck:
    """Walk the whole chain in batches of ``_VERIFY_BATCH`` events."""
    prev, total, after = GENESIS_HASH, 0, 0
    while True:
        rows = (
            await session.execute(
                # Plain rows, not entities: keeps a long walk out of the identity map.
                select(*AuditEvent.__table__.c)
                .where(AuditEvent.seq > after)
                .order_by(AuditEvent.seq)
                .limit(_VERIFY_BATCH)
            )
        ).all()
        if not rows:
            return ChainCheck(True, total, prev)
        result = verify_events(rows, prev)
        total += result.checked
        if not result.ok:
            return ChainCheck(False, total, result.last_hash, result.broken_at_seq, result.reason)
        prev, after = result.last_hash, rows[-1].seq


async def list_events(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    action: str | None = None,
    actor_id: uuid.UUID | None = None,
    object_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> tuple[list[AuditEvent], int]:
    conditions = []
    if action:
        conditions.append(AuditEvent.action == action)
    if actor_id:
        conditions.append(AuditEvent.actor_id == actor_id)
    if object_id:
        conditions.append(AuditEvent.object_id == object_id)
    if since:
        conditions.append(AuditEvent.occurred_at >= since)
    if until:
        conditions.append(AuditEvent.occurred_at < until)
    total = (
        await session.execute(select(func.count()).select_from(AuditEvent).where(*conditions))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(AuditEvent)
                .where(*conditions)
                .order_by(AuditEvent.seq.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total
