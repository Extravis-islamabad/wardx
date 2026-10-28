"""Audit trail: append-only in the database, and tamper-evident through the hash chain.

The triggers stop ordinary writes; the chain catches someone who gets past them
(a superuser disabling the trigger). Each test restores what it changes, so the
chain verifies again for later tests.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from src.core.db import session_factory


async def _verify(client, admin) -> dict:
    return (await client.post("/audit/verify", headers=admin)).json()["data"]


async def _ensure_events(client, admin, n: int = 12) -> None:
    for i in range(n):
        await client.get("/targets", headers=admin, params={"search": f"audit-{i}"})
        await client.post(
            "/targets",
            headers=admin,
            json={
                "name": f"audit-int-{i}",
                "address": "10.8.0.1",
                "platform": "linux",
                "protocol": "ssh",
            },
        )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit.events SET action = 'x' WHERE seq = 1",
        "UPDATE audit.events SET hash = repeat('0', 64)",
        "DELETE FROM audit.events WHERE seq = 1",
        "DELETE FROM audit.events",
        "TRUNCATE audit.events",
    ],
)
async def test_changes_are_refused_by_the_database(client, admin, statement):
    await _ensure_events(client, admin, 1)
    async with session_factory()() as session:
        with pytest.raises(Exception, match="append-only"):
            await session.execute(text(statement))
        await session.rollback()
    assert (await _verify(client, admin))["ok"] is True


async def test_every_action_is_audited_including_failures(client, admin):
    before = (await client.get("/audit/events", headers=admin)).json()["total"]
    resp = await client.post("/auth/login", json={"username": "admin", "password": "wrong-pw-1"})
    assert resp.status_code == 401
    events = (
        await client.get("/audit/events", headers=admin, params={"action": "auth.login"})
    ).json()["data"]
    assert events[0]["outcome"] == "failure"
    assert (await client.get("/audit/events", headers=admin)).json()["total"] > before


class _TriggersOff:
    """Simulates an attacker with database superuser rights."""

    def __init__(self, session) -> None:
        self.session = session

    async def __aenter__(self):
        await self.session.execute(text("ALTER TABLE audit.events DISABLE TRIGGER USER"))
        return self.session

    async def __aexit__(self, *exc):
        await self.session.execute(text("ALTER TABLE audit.events ENABLE TRIGGER USER"))
        await self.session.commit()


async def _middle_seq(session) -> int:
    return (
        await session.execute(text("SELECT seq FROM audit.events ORDER BY seq OFFSET 5 LIMIT 1"))
    ).scalar_one()


async def test_edited_event_is_detected(client, admin):
    await _ensure_events(client, admin)
    async with session_factory()() as session:
        seq = await _middle_seq(session)
        original = (
            await session.execute(
                text("SELECT actor_name FROM audit.events WHERE seq = :s"), {"s": seq}
            )
        ).scalar_one()
        async with _TriggersOff(session):
            await session.execute(
                text("UPDATE audit.events SET actor_name = 'someone-else' WHERE seq = :s"),
                {"s": seq},
            )
        result = await _verify(client, admin)
        assert result["ok"] is False and result["broken_at_seq"] == seq
        async with _TriggersOff(session):
            await session.execute(
                text("UPDATE audit.events SET actor_name = :a WHERE seq = :s"),
                {"a": original, "s": seq},
            )
    assert (await _verify(client, admin))["ok"] is True


async def test_deleted_event_in_the_middle_is_detected(client, admin):
    await _ensure_events(client, admin)
    async with session_factory()() as session:
        seq = await _middle_seq(session)
        row = (
            (await session.execute(text("SELECT * FROM audit.events WHERE seq = :s"), {"s": seq}))
            .mappings()
            .one()
        )
        async with _TriggersOff(session):
            await session.execute(text("DELETE FROM audit.events WHERE seq = :s"), {"s": seq})
        result = await _verify(client, admin)
        assert result["ok"] is False and result["broken_at_seq"] is not None
        async with _TriggersOff(session):
            cols = ", ".join(row.keys())
            await session.execute(
                text(
                    f"INSERT INTO audit.events ({cols}) VALUES "  # noqa: S608 - column names from the row
                    f"({', '.join(':' + k for k in row.keys())})"
                ).bindparams(),
                {k: (v if k != "details" else __import__("json").dumps(v)) for k, v in row.items()},
            )
    assert (await _verify(client, admin))["ok"] is True


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known gap: a pure hash chain cannot tell that its newest events were removed. "
        "Needs an external anchor of the chain head (periodic signed checkpoint kept outside "
        "the tenant DB / shipped to SIEM). When that lands this test passes and strict xfail "
        "fails the run, so the marker gets removed."
    ),
)
async def test_truncated_tail_is_detected(client, admin):
    await _ensure_events(client, admin)
    async with session_factory()() as session:
        last = (
            (await session.execute(text("SELECT * FROM audit.events ORDER BY seq DESC LIMIT 1")))
            .mappings()
            .one()
        )
        async with _TriggersOff(session):
            await session.execute(
                text("DELETE FROM audit.events WHERE seq = :s"), {"s": last["seq"]}
            )
        try:
            assert (await _verify(client, admin))["ok"] is False
        finally:
            async with _TriggersOff(session):
                cols = ", ".join(last.keys())
                await session.execute(
                    text(
                        f"INSERT INTO audit.events ({cols}) VALUES "  # noqa: S608
                        f"({', '.join(':' + k for k in last.keys())})"
                    ),
                    {
                        k: (v if k != "details" else __import__("json").dumps(v))
                        for k, v in last.items()
                    },
                )
