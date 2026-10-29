"""Backup archives and restore verification through the wardx CLI (HA_DR.md §7)."""

from __future__ import annotations

import json

import pytest

from src.cli.main import run
from src.keys.runtime import key_provider
from tests.integration.ha.ha_support import rows

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _cli(*argv: str) -> tuple[int, list[str]]:
    lines: list[str] = []
    return await run(list(argv), init=False, out=lines.append), lines


async def test_backup_encrypt_decrypt_files(app, tmp_path):
    assert key_provider() is not None
    plain = tmp_path / "base.tar"
    plain.write_bytes(b"PGDMP" + bytes(range(256)) * 600)
    enc, back = tmp_path / "base.tar.wxbak", tmp_path / "restored.tar"
    assert (
        await _cli("backup", "encrypt", "--name", "base.tar", "--in", str(plain), "--out", str(enc))
    )[0] == 0
    assert b"PGDMP" not in enc.read_bytes()
    assert (await _cli("backup", "decrypt", "--in", str(enc), "--out", str(back)))[0] == 0
    assert back.read_bytes() == plain.read_bytes()


async def test_restore_verify_and_drill_recorded(app, client, admin, tmp_path):
    # The test database stands in for a restored scratch copy.
    result_file = tmp_path / "result.json"
    code, lines = await _cli(
        "restore",
        "verify",
        "--restore-point",
        "2000-01-01T00:00:00+00:00",
        "--sample",
        "5",
        "--json",
        str(result_file),
    )
    result = json.loads(result_file.read_text())
    assert code == 0 and result["ok"] is True
    assert result["audit_chain"]["ok"] is True and result["audit_chain"]["checked"] > 0
    assert result["secrets_failed"] == 0
    assert isinstance(result["rotated_after_restore_point"], list)

    code, lines = await _cli("restore", "record-drill", "--result", str(result_file))
    assert code == 0 and "recorded: ok" in lines[-1]
    drill = (await client.get("/health/cluster", headers=admin)).json()["data"][
        "last_restore_drill"
    ]
    assert drill["ok"] is True
    audited = await rows(
        "SELECT outcome FROM audit.events WHERE action = 'backup.restore_drill' "
        "ORDER BY seq DESC LIMIT 1"
    )
    assert audited == [("success",)]
