"""Encrypted recordings in the object store (HA_DR.md §5, §5.1), local-filesystem store."""

from __future__ import annotations

import asyncio

import asyncssh
import pytest

from src.dependencies.sessions import recording_store
from src.services.session_recordings.recording_objects import final_key, spool_prefix
from tests.conftest import DEVICE_USER
from tests.integration.ha.ha_support import execute, rows

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _session(gateway) -> str:
    conn = await asyncssh.connect(
        "127.0.0.1",
        gateway.port,
        username=f"netops1%{DEVICE_USER}%fake-rtr",
        password="User-Passw0rd-netops1",
        known_hosts=None,
        client_keys=None,
        agent_path=None,
        config=None,
        preferred_auth="password",
    )
    result = await conn.run("show version", timeout=5)
    assert result.exit_status == 0
    conn.close()
    for _ in range(50):
        found = await rows(
            "SELECT s.id, s.status FROM access.sessions s JOIN iam.users u ON u.id = s.user_id "
            "WHERE u.username = 'netops1' ORDER BY s.started_at DESC LIMIT 1"
        )
        if found and found[0][1] != "active":
            return str(found[0][0])
        await asyncio.sleep(0.1)
    raise AssertionError("session did not close")


async def test_recording_is_encrypted_stored_and_replayed(gateway, lab, client, admin):
    sid = await _session(gateway)
    row = (
        await rows(
            "SELECT recording_key, recording_encrypted, recording_incomplete, recording_sha256, "
            "recording_ciphertext_sha256, recording_path FROM access.sessions WHERE id = :i",
            i=sid,
        )
    )[0]
    key, encrypted, incomplete, plain_sha, cipher_sha, path = row
    assert key == f"recordings/{sid}.wxrec" and encrypted and not incomplete
    assert plain_sha and cipher_sha and plain_sha != cipher_sha and path is None
    store = recording_store()
    data = await store.get(key)
    assert b"show version" not in data and b'"version": 2' not in data
    assert await store.list(spool_prefix(sid)) == []  # chunk objects removed

    resp = await client.get(f"/sessions/{sid}/recording", headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.headers["x-wardx-recording-verified"] == "true"
    assert resp.headers["x-wardx-recording-encrypted"] == "true"
    assert resp.headers["x-wardx-recording-incomplete"] == "false"
    assert resp.text.startswith('{"version": 2')
    detail = (await client.get(f"/sessions/{sid}", headers=admin)).json()["data"]
    assert detail["recording_encrypted"] is True and detail["has_recording"] is True


async def test_tampered_or_truncated_recording_is_refused(gateway, lab, client, admin):
    sid = await _session(gateway)
    store = recording_store()
    key = final_key(sid)
    original = await store.get(key)
    try:
        flipped = bytearray(original)
        flipped[-5] ^= 0x01
        await store.put(key, bytes(flipped))
        resp = await client.get(f"/sessions/{sid}/recording", headers=admin)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "recording_integrity_failed"
        # Dropping the final chunk of a finished recording is refused as truncation.
        await store.put(key, original[: len(original) - 20 - 4])
        resp = await client.get(f"/sessions/{sid}/recording", headers=admin)
        assert resp.status_code == 409
        await store.delete(key)
        resp = await client.get(f"/sessions/{sid}/recording", headers=admin)
        assert resp.status_code == 404
    finally:
        await store.put(key, original)
    assert (await client.get(f"/sessions/{sid}/recording", headers=admin)).status_code == 200


async def test_legacy_plaintext_recording_still_replays(client, admin, gateway, lab, tmp_path):
    sid = await _session(gateway)
    plain = (
        await client.get(f"/sessions/{sid}/recording", headers=admin)
    ).content  # decrypted asciicast
    legacy = gateway.recording_dir / f"{sid}.cast"
    legacy.write_bytes(plain)
    await execute(
        "UPDATE access.sessions SET recording_key = NULL, recording_encrypted = FALSE, "
        "recording_path = :p WHERE id = :i",
        p=str(legacy),
        i=sid,
    )
    resp = await client.get(f"/sessions/{sid}/recording", headers=admin)
    assert resp.status_code == 200
    assert resp.headers["x-wardx-recording-encrypted"] == "false"
    assert resp.headers["x-wardx-recording-verified"] == "true"
