"""`wardx dr post-failover-check` (HA_DR.md §6.1) against the fake rotation device."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from src.cli.main import run
from src.models import utcnow
from tests.integration.ha.ha_support import rows
from tests.integration.rotation.rotation_support import sql

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _cli(*argv: str) -> tuple[int, list[str]]:
    lines: list[str] = []
    code = await run(list(argv), init=False, out=lines.append)
    return code, lines


def _line(lines: list[str], account_id: str) -> list[str]:
    return [line for line in lines if account_id in line]


async def test_lists_window_verifies_and_reconciles(rotlab, client, admin, tmp_path):
    before = await rotlab.account()
    await rotlab.run((await rotlab.request(before["id"]))["id"])
    await asyncio.sleep(0.05)
    since = utcnow()

    ok = await rotlab.account()
    await rotlab.run((await rotlab.request(ok["id"]))["id"])
    drifted = await rotlab.account()
    helper = await rotlab.account(target=drifted["target"])
    resp = await client.patch(
        f"/accounts/{drifted['id']}", headers=admin, json={"reconcile_account_id": helper["id"]}
    )
    assert resp.status_code == 200, resp.text
    await rotlab.run((await rotlab.request(drifted["id"]))["id"])
    lonely = await rotlab.account()  # no reconcile account
    await rotlab.run((await rotlab.request(lonely["id"]))["id"])
    # After failover the devices hold passwords this vault does not know (lost commits).
    rotlab.device.passwords[drifted["username"]] = "Changed-After-Failover-1"
    rotlab.device.passwords[lonely["username"]] = "Changed-After-Failover-2"

    # A rotation only the forwarded export saw (an account the DR copy never got).
    ghost = str(uuid.uuid4())
    export = tmp_path / "audit.jsonl"
    export.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "action": "rotation.succeeded",
                        "occurred_at": utcnow().isoformat(),
                        "details": {"account_id": ghost, "reason": "schedule"},
                    }
                ),
                "not json",
                json.dumps({"action": "rotation.verify", "occurred_at": utcnow().isoformat()}),
            ]
        )
    )

    # Dry run: lists, queues nothing.
    jobs_before = (await sql("SELECT count(*) AS n FROM access.rotation_jobs"))[0]["n"]
    code, lines = await _cli(
        "dr",
        "post-failover-check",
        "--since",
        since.isoformat(),
        "--audit-export",
        str(export),
        "--dry-run",
    )
    assert code == 0
    for acc in (ok, drifted, lonely):
        assert _line(lines, acc["id"]), acc
    assert any("UNKNOWN HERE" in line for line in _line(lines, ghost))
    assert not _line(lines, before["id"])
    assert any("1 unreadable skipped" in line for line in lines)
    assert (await sql("SELECT count(*) AS n FROM access.rotation_jobs"))[0]["n"] == jobs_before

    # The real run: verifies run (the worker ticks alongside), failures are reconciled.
    stop = asyncio.Event()

    async def worker():
        while not stop.is_set():
            await rotlab.tick()
            await asyncio.sleep(0.2)

    ticking = asyncio.create_task(worker())
    try:
        code, lines = await _cli(
            "dr",
            "post-failover-check",
            "--since",
            since.isoformat(),
            "--audit-export",
            str(export),
            "--wait-seconds",
            "8",
        )
    finally:
        stop.set()
        await ticking
    report = lines[lines.index("Report:") :]
    assert code == 1  # not everything verified
    assert any(f"{ok['username']}" in r and r.endswith(": verified") for r in report)
    assert any(drifted["username"] in r and "reconcile queued" in r for r in report)
    assert any(
        lonely["username"] in r and "no reconcile account; flagged out of sync" in r for r in report
    )
    assert any("?@?" in r and "manual" in r for r in report)
    status = (
        await sql("SELECT sync_status FROM inventory.accounts WHERE id = :i", i=lonely["id"])
    )[0]["sync_status"]
    assert status == "out_of_sync"
    reconcile = await sql(
        "SELECT reason, status FROM access.rotation_jobs WHERE account_id = :i "
        "ORDER BY created_at DESC LIMIT 1",
        i=drifted["id"],
    )
    assert reconcile[0]["reason"] == "reconcile"
    runs = await rows(
        "SELECT details->>'dry_run', outcome FROM audit.events "
        "WHERE action = 'dr.post_failover_check' ORDER BY seq DESC LIMIT 2"
    )
    assert runs == [("false", "failure"), ("true", "success")]
    # Let the queued reconcile finish so later tests start clean.
    await rotlab.run(
        str(
            (
                await sql(
                    "SELECT id FROM access.rotation_jobs "
                    "WHERE account_id = :i AND reason = 'reconcile'",
                    i=drifted["id"],
                )
            )[0]["id"]
        )
    )
