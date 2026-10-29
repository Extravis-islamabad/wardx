"""`wardx recordings encrypt` on recordings the test creates (HA_DR.md §5.1)."""

from __future__ import annotations

import pytest

from src.cli.main import run
from src.dependencies.sessions import recording_store
from tests.integration.ha.ha_support import execute, rows, scalar
from tests.integration.ha.test_recordings import _session

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _make_legacy(gateway, client, admin) -> tuple[str, object]:
    """A finished session turned back into a legacy plaintext recording."""
    sid = await _session(gateway)
    plain = (await client.get(f"/sessions/{sid}/recording", headers=admin)).content
    path = gateway.recording_dir / f"legacy-{sid}.cast"
    path.write_bytes(plain)
    await recording_store().delete(f"recordings/{sid}.wxrec")
    await execute(
        "UPDATE access.sessions SET recording_key = NULL, recording_encrypted = FALSE, "
        "recording_ciphertext_sha256 = NULL, recording_path = :p WHERE id = :i",
        p=str(path),
        i=sid,
    )
    return sid, path


async def _cli(*argv: str) -> tuple[int, list[str]]:
    lines: list[str] = []
    code = await run(list(argv), init=False, out=lines.append)
    return code, lines


async def test_encrypt_verifies_keeps_originals_then_removes_on_request(
    gateway, lab, client, admin
):
    good, good_path = await _make_legacy(gateway, client, admin)
    bad, bad_path = await _make_legacy(gateway, client, admin)
    bad_path.write_bytes(bad_path.read_bytes() + b'[9.9, "o", "edited later"]\n')

    code, lines = await _cli("recordings", "encrypt")
    assert code == 1  # one failed
    assert any(line == f"migrated  {good}" for line in lines)
    assert any(line.startswith(f"FAILED    {bad}") for line in lines)

    # The good one: encrypted copy verified, original kept, replay from the store.
    enc, key, removed = (
        await rows(
            "SELECT recording_encrypted, recording_key, recording_original_removed_at "
            "FROM access.sessions WHERE id = :i",
            i=good,
        )
    )[0]
    assert enc and key == f"recordings/{good}.wxrec" and removed is None
    assert good_path.exists()
    resp = await client.get(f"/sessions/{good}/recording", headers=admin)
    assert resp.headers["x-wardx-recording-encrypted"] == "true"
    assert resp.headers["x-wardx-recording-verified"] == "true"
    # The altered one: original untouched, no unverified copy left, not marked.
    assert bad_path.read_bytes().endswith(b'edited later"]\n')
    assert not await recording_store().exists(f"recordings/{bad}.wxrec")
    assert not await scalar("SELECT recording_encrypted FROM access.sessions WHERE id = :i", i=bad)
    audited = await rows(
        "SELECT action, outcome, safe_id FROM audit.events WHERE object_id IN (:a, :b) "
        "AND action LIKE 'session.recording_encrypt%'",
        a=good,
        b=bad,
    )
    assert {(a, o) for a, o, _ in audited} == {
        ("session.recording_encrypted", "success"),
        ("session.recording_encrypt_failed", "failure"),
    }
    assert all(safe is not None for *_, safe in audited)

    # Resumable: a second run does nothing new for the migrated one.
    code, lines = await _cli("recordings", "encrypt")
    assert not any(str(good) in line for line in lines)

    # Originals go only on the separate, explicit run, only for verified copies.
    code, lines = await _cli("recordings", "encrypt", "--remove-verified-originals")
    assert any(line.startswith(f"removed   {good}") for line in lines)
    assert not good_path.exists()
    assert bad_path.exists()
    assert await scalar(
        "SELECT recording_original_removed_at IS NOT NULL FROM access.sessions WHERE id = :i",
        i=good,
    )
    resp = await client.get(f"/sessions/{good}/recording", headers=admin)
    assert resp.status_code == 200 and resp.headers["x-wardx-recording-verified"] == "true"
    # Leave no legacy rows for later tests to trip over.
    await execute("UPDATE access.sessions SET recording_path = NULL WHERE id = :i", i=bad)
    bad_path.unlink()
