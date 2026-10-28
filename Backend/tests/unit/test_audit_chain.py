import os
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from src.services.audit.audit_chain import (
    GENESIS_HASH,
    canonical,
    chain_hash,
    event_hash,
    verify_events,
)


@dataclass
class Ev:
    seq: int
    id: uuid.UUID
    occurred_at: datetime
    action: str
    actor_id: uuid.UUID | None = None
    actor_name: str | None = "alice"
    object_type: str | None = "account"
    object_id: uuid.UUID | None = None
    outcome: str = "success"
    source_ip: str | None = "10.0.0.1"
    details: dict = field(default_factory=dict)
    prev_hash: str = ""
    hash: str = ""
    key_version: int | None = 1


KEY = os.urandom(32)
KEYS = {1: KEY}


def _chain(n: int, *, legacy: int = 0) -> list[Ev]:
    """``n`` events; the first ``legacy`` are unkeyed SHA-256, the rest HMAC'd with KEY."""
    prev, out = GENESIS_HASH, []
    t0 = datetime(2026, 10, 1, tzinfo=UTC)
    for i in range(n):
        ev = Ev(
            seq=i + 1,
            id=uuid.uuid4(),
            occurred_at=t0 + timedelta(seconds=i),
            action=f"a{i}",
            details={"n": i},
            key_version=None if i < legacy else 1,
        )
        ev.prev_hash = prev
        ev.hash = event_hash(ev, prev, None if i < legacy else KEY)
        prev = ev.hash
        out.append(ev)
    return out


def test_intact_chain_verifies():
    result = verify_events(_chain(5), keys=KEYS)
    assert result.ok and result.checked == 5


def test_edited_event_breaks_chain_at_that_event():
    events = _chain(5)
    events[2] = replace(events[2], details={"n": 999})
    result = verify_events(events, keys=KEYS)
    assert not result.ok and result.broken_at_seq == 3 and result.checked == 2


def test_deleted_event_breaks_link():
    events = _chain(5)
    del events[1]
    result = verify_events(events, keys=KEYS)
    assert not result.ok and result.broken_at_seq == 3


def test_rehashed_edit_still_detected_by_next_link():
    events = _chain(4)
    forged = replace(events[1], action="forged")
    forged.hash = event_hash(forged, forged.prev_hash, KEY)
    events[1] = forged
    result = verify_events(events, keys=KEYS)
    assert not result.ok and result.broken_at_seq == 3


def test_canonical_is_key_order_and_timezone_independent():
    eid = uuid.uuid4()
    ts = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    common = dict(
        event_id=eid,
        actor_id=None,
        actor_name="x",
        action="a",
        object_type=None,
        object_id=None,
        outcome="success",
        source_ip=None,
    )
    a = canonical(occurred_at=ts, details={"b": 1, "a": 2}, **common)
    b = canonical(occurred_at=ts.astimezone(), details={"a": 2, "b": 1}, **common)
    assert a == b
    assert chain_hash(GENESIS_HASH, a) == chain_hash(GENESIS_HASH, b)


def test_wrong_key_fails():
    result = verify_events(_chain(3), keys={1: os.urandom(32)})
    assert not result.ok and result.broken_at_seq == 1


def test_missing_key_version_fails():
    result = verify_events(_chain(3), keys={})
    assert not result.ok and "not available" in result.reason


def test_chain_recomputed_without_the_key_fails():
    """A DB superuser recomputing the chain with plain SHA-256 as 'legacy' is caught."""
    events, prev = _chain(4), GENESIS_HASH
    for ev in events:
        ev.key_version = None
        ev.prev_hash = prev
        ev.hash = event_hash(ev, prev)
        prev = ev.hash
    result = verify_events(events, keys=KEYS, legacy_max_seq=0)
    assert not result.ok and result.broken_at_seq == 1
    assert result.reason == "unkeyed event outside the legacy segment"


def test_legacy_segment_then_keyed_verifies():
    result = verify_events(_chain(6, legacy=3), keys=KEYS, legacy_max_seq=3)
    assert result.ok and result.checked == 6 and result.keyed_seen


def test_unkeyed_event_after_keyed_fails_even_inside_boundary():
    events = _chain(4, legacy=1)
    forged = replace(events[2], key_version=None)
    forged.hash = event_hash(forged, forged.prev_hash)
    events[2] = forged
    events[3].prev_hash = forged.hash
    result = verify_events(events, keys=KEYS, legacy_max_seq=99)
    assert not result.ok and result.broken_at_seq == 3


def test_keyed_seen_carries_across_batches():
    events = _chain(4, legacy=2)
    first = verify_events(events[:3], keys=KEYS, legacy_max_seq=2)
    assert first.ok and first.keyed_seen
    late = replace(events[3], key_version=None)
    late.hash = event_hash(late, late.prev_hash)
    result = verify_events(
        [late], first.last_hash, keys=KEYS, legacy_max_seq=99, keyed_seen=first.keyed_seen
    )
    assert not result.ok
