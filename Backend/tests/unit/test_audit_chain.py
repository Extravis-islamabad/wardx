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


def _chain(n: int) -> list[Ev]:
    prev, out = GENESIS_HASH, []
    t0 = datetime(2026, 10, 1, tzinfo=UTC)
    for i in range(n):
        ev = Ev(
            seq=i + 1,
            id=uuid.uuid4(),
            occurred_at=t0 + timedelta(seconds=i),
            action=f"a{i}",
            details={"n": i},
        )
        ev.prev_hash = prev
        ev.hash = event_hash(ev, prev)
        prev = ev.hash
        out.append(ev)
    return out


def test_intact_chain_verifies():
    result = verify_events(_chain(5))
    assert result.ok and result.checked == 5


def test_edited_event_breaks_chain_at_that_event():
    events = _chain(5)
    events[2] = replace(events[2], details={"n": 999})
    result = verify_events(events)
    assert not result.ok and result.broken_at_seq == 3 and result.checked == 2


def test_deleted_event_breaks_link():
    events = _chain(5)
    del events[1]
    result = verify_events(events)
    assert not result.ok and result.broken_at_seq == 3


def test_rehashed_edit_still_detected_by_next_link():
    events = _chain(4)
    forged = replace(events[1], action="forged")
    forged.hash = event_hash(forged, forged.prev_hash)
    events[1] = forged
    result = verify_events(events)
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
