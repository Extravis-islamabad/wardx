"""Hash chain over audit events: canonical form, hashing and verification.

Keyed events: hash = HMAC-SHA256(audit key, prev_hash || canonical JSON), with
the key version inside the canonical JSON. The audit key lives only wrapped by
the key provider, so database access alone cannot recompute a valid chain
(Backend/TENANCY_KEYS.md §8.1).

Legacy events (key_version NULL) were hashed with plain SHA-256 before the
chain was keyed. They are accepted only up to a boundary pinned outside the
database (``audit_legacy_max_seq``) and never after a keyed event, so a chain
rewritten as "legacy" fails.

The database sequence number is left out of the hash because it is assigned
after the hash is computed; order is still fixed, because each hash commits to
the one before it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Iterable, Mapping
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
    key_version: int | None


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
    key_version: int | None = None,
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
    if key_version is not None:
        # Only keyed events carry it, so legacy hashes stay exactly as they were.
        payload["key_version"] = key_version
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def chain_hash(prev_hash: str, body: bytes, key: bytes | None = None) -> str:
    """HMAC-SHA256 under ``key``; plain SHA-256 only for legacy events (key None)."""
    data = prev_hash.encode() + body
    if key is None:
        return hashlib.sha256(data).hexdigest()
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def event_hash(event: ChainedEvent, prev_hash: str, key: bytes | None = None) -> str:
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
            key_version=event.key_version,
        ),
        key,
    )


@dataclass(frozen=True)
class ChainCheck:
    ok: bool
    checked: int
    last_hash: str
    broken_at_seq: int | None = None
    reason: str | None = None
    keyed_seen: bool = False


def verify_events(
    events: Iterable[ChainedEvent],
    prev_hash: str = GENESIS_HASH,
    *,
    keys: Mapping[int, bytes] | None = None,
    legacy_max_seq: int = 0,
    keyed_seen: bool = False,
) -> ChainCheck:
    """Check a run of events in sequence order, continuing from ``prev_hash``.

    ``keys`` maps audit-key versions to keys. ``keyed_seen`` carries over from
    an earlier batch whether a keyed event has already appeared.
    """
    keys = keys or {}
    checked = 0
    for event in events:
        if event.prev_hash != prev_hash:
            return ChainCheck(False, checked, prev_hash, event.seq, "previous-hash link broken")
        if event.key_version is None:
            if keyed_seen or event.seq > legacy_max_seq:
                return ChainCheck(
                    False, checked, prev_hash, event.seq, "unkeyed event outside the legacy segment"
                )
            key = None
        else:
            key = keys.get(event.key_version)
            if key is None:
                return ChainCheck(
                    False,
                    checked,
                    prev_hash,
                    event.seq,
                    f"audit key version {event.key_version} is not available",
                )
            keyed_seen = True
        if event_hash(event, prev_hash, key) != event.hash:
            return ChainCheck(False, checked, prev_hash, event.seq, "content does not match hash")
        prev_hash = event.hash
        checked += 1
    return ChainCheck(True, checked, prev_hash, keyed_seen=keyed_seen)
