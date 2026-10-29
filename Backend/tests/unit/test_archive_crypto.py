"""Encrypted backup archives (HA_DR.md §7): round trip, and any tampering refused."""

from __future__ import annotations

import io
import os

import pytest

from src.keys.file_provider import FileKeyProvider
from src.services.backup.archive_crypto import (
    CHUNK,
    ArchiveIntegrityError,
    decrypt_stream,
    encrypt_stream,
)

KEK = FileKeyProvider(os.urandom(32))


async def _enc(data: bytes, name: str = "wardx-base-1.tar") -> bytes:
    out = io.BytesIO()
    assert await encrypt_stream(KEK, name, io.BytesIO(data), out) == len(data)
    return out.getvalue()


async def _dec(blob: bytes, provider=KEK) -> bytes:
    out = io.BytesIO()
    await decrypt_stream(provider, io.BytesIO(blob), out)
    return out.getvalue()


@pytest.mark.parametrize("size", [0, 1, CHUNK, CHUNK * 3 + 17])
async def test_round_trip(size):
    data = os.urandom(size)
    blob = await _enc(data)
    assert await _dec(blob) == data
    if size:
        assert data[:64] not in blob


async def test_tampering_truncation_and_wrong_kek_fail():
    data = os.urandom(CHUNK * 2 + 5)
    blob = await _enc(data)
    flipped = bytearray(blob)
    flipped[-3] ^= 1
    with pytest.raises(ArchiveIntegrityError):
        await _dec(bytes(flipped))
    with pytest.raises(ArchiveIntegrityError):
        await _dec(blob[: len(blob) - 10])  # cut inside the last chunk
    last = 4 + 5 + 16
    with pytest.raises(ArchiveIntegrityError, match="no final chunk"):
        await _dec(blob[: len(blob) - last])  # whole final chunk dropped
    with pytest.raises(ArchiveIntegrityError):
        await _dec(blob, FileKeyProvider(os.urandom(32)))
    with pytest.raises(ArchiveIntegrityError):
        await _dec(b"not an archive")


async def test_retired_kek_still_opens_after_rotation():
    blob = await _enc(b"base backup bytes")
    old = KEK._keys[KEK.active_key_id]  # test only: build a rotated provider
    rotated = FileKeyProvider(os.urandom(32), [old])
    assert await _dec(blob, rotated) == b"base backup bytes"
