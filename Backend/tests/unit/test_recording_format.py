"""The encrypted recording format (HA_DR.md §5.1): any reordered, dropped, appended or
edited byte fails; a recording without its final chunk decrypts as incomplete."""

from __future__ import annotations

import os
import uuid

import pytest

from src.services.recordings.recording_format import (
    CHUNK_MAX,
    RecordingEncryptor,
    RecordingIntegrityError,
    decrypt,
)

FILES_KEY = os.urandom(32)


def _record(chunks: list[bytes], *, final: bool = True, rid=None):
    rid = rid or uuid.uuid4()
    enc = RecordingEncryptor(rid, 1, FILES_KEY)
    frames = [enc.chunk(c) for c in chunks[:-1]]
    frames.append(enc.chunk(chunks[-1], final=final))
    return rid, enc.header, frames


def test_round_trip_and_no_plaintext_in_object():
    rid, header, frames = _record([b'{"version": 2}\n', b"secret output" * 10, b""])
    data = header + b"".join(frames)
    out = decrypt(data, FILES_KEY, rid)
    assert out.complete and out.chunks == 3
    assert out.plaintext == b'{"version": 2}\n' + b"secret output" * 10
    assert b"secret output" not in data and b'{"version": 2}' not in data


def test_chunk_size_limit():
    enc = RecordingEncryptor(uuid.uuid4(), 1, FILES_KEY)
    with pytest.raises(ValueError):
        enc.chunk(b"x" * (CHUNK_MAX + 1))


@pytest.mark.parametrize("position", ["header", "chunk", "tag"])
def test_any_flipped_byte_fails(position):
    rid, header, frames = _record([b"a" * 100, b"b" * 100])
    data = bytearray(header + b"".join(frames))
    index = {"header": len(header) - 5, "chunk": len(header) + 10, "tag": len(data) - 1}[position]
    data[index] ^= 0x01
    with pytest.raises(RecordingIntegrityError):
        decrypt(bytes(data), FILES_KEY, rid)


def test_reordered_dropped_appended_chunks_fail():
    rid, header, frames = _record([b"one", b"two", b"three", b"end"])
    with pytest.raises(RecordingIntegrityError):
        decrypt(header + frames[1] + frames[0] + frames[2] + frames[3], FILES_KEY, rid)
    with pytest.raises(RecordingIntegrityError):
        decrypt(header + frames[0] + frames[2] + frames[3], FILES_KEY, rid)
    with pytest.raises(RecordingIntegrityError):
        decrypt(header + b"".join(frames) + frames[1], FILES_KEY, rid)
    with pytest.raises(RecordingIntegrityError):
        decrypt(header + b"".join(frames)[:-3], FILES_KEY, rid)  # cut inside a chunk


def test_missing_final_chunk_is_incomplete_not_complete():
    rid, header, frames = _record([b"one", b"two", b"end"])
    out = decrypt(header + frames[0] + frames[1], FILES_KEY, rid)
    assert out.complete is False and out.plaintext == b"onetwo"
    # A recording cut off by a lost node: no final flag anywhere.
    rid, header, frames = _record([b"one", b"two"], final=False)
    assert decrypt(header + b"".join(frames), FILES_KEY, rid).complete is False


def test_wrong_key_or_other_recording_fails():
    rid, header, frames = _record([b"one"])
    data = header + b"".join(frames)
    with pytest.raises(RecordingIntegrityError):
        decrypt(data, os.urandom(32), rid)
    with pytest.raises(RecordingIntegrityError):
        decrypt(data, FILES_KEY, uuid.uuid4())
    # Another recording's header in front of these chunks.
    _, other_header, _ = _record([b"x"])
    with pytest.raises(RecordingIntegrityError):
        decrypt(other_header + b"".join(frames), FILES_KEY)
