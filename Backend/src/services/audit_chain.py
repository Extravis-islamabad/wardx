"""Hash chain over audit events: canonical form, hashing and verification.

hash = SHA-256(prev_hash || canonical JSON of the event's fields). The database
sequence number is left out because it is assigned after the hash is computed;
order is still fixed, because each hash commits to the one before it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

GENESIS_HASH = "0" * 64


class ChainedEvent(Protocol):
    seq: int
    id: Any
    occurred_at: datetime
    actor_id: Any
    actor_name: str | None
    action: str
    object_type: str | None
    object_id: Any
    outcome: str
    source_ip: str | None
    details: dict[str, Any]
    prev_hash: str
    hash: str


def _opt_str(value: Any) -> str | None:
    return None if value is None else str(value)


def canonical(
    *,
    event_id: Any,
    occurred_at: datetime,
    actor_id: Any,
    actor_name: str | None,
    action: str,
    object_type: str | None,
    object_id: Any,
    outcome: str,
    source_ip: str | None,
    details: dict[str, Any],
) -> bytes:
    payload = {
        "id": str(event_id),
        "occurred_at": occurred_at.astimezone(UTC).isoformat(timespec="microseconds"),
        "actor_id": _opt_str(actor_id),
        "actor_name": actor_name,
        "action": action,
        "object_type": object_type,
        "object_id": _opt_str(object_id),
        "outcome": outcome,
        "source_ip": source_ip,
        "details": details,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def chain_hash(prev_hash: str, body: bytes) -> str:
    return hashlib.sha256(prev_hash.encode() + body).hexdigest()


def event_hash(event: ChainedEvent, prev_hash: str) -> str:
    return chain_hash(
        prev_hash,
        canonical(
            event_id=event.id,
            occurred_at=event.occurred_at,
            actor_id=event.actor_id,
            actor_name=event.actor_name,
            action=event.action,
            object_type=event.object_type,
            object_id=event.object_id,
            outcome=event.outcome,
            source_ip=event.source_ip,
            details=event.details,
        ),
    )


@dataclass(frozen=True)
class ChainCheck:
    ok: bool
    checked: int
    last_hash: str
    broken_at_seq: int | None = None
    reason: str | None = None


def verify_events(events: Iterable[ChainedEvent], prev_hash: str = GENESIS_HASH) -> ChainCheck:
    """Check a run of events in sequence order, continuing from ``prev_hash``."""
    checked = 0
    for event in events:
        if event.prev_hash != prev_hash:
            return ChainCheck(False, checked, prev_hash, event.seq, "previous-hash link broken")
        if event_hash(event, prev_hash) != event.hash:
            return ChainCheck(False, checked, prev_hash, event.seq, "content does not match hash")
        prev_hash = event.hash
        checked += 1
    return ChainCheck(True, checked, prev_hash)
