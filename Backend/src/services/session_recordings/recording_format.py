"""The encrypted recording format, v1 (HA_DR.md §5.1).

    object  = header frame, then chunk frames
    header  = b"WXREC" 0x01 | u32 length | JSON {format, recording_id, files_key_version,
              dek_nonce, wrapped_dek, nonce_prefix, chunk_max}
    chunk   = u32 length | AES-256-GCM ciphertext and tag of at most 64 KiB of plaintext

- Each recording has a fresh 256-bit DEK, wrapped by the tenant's ``files`` key (version in
  the header) with AAD naming the recording, so a header moved to another recording fails.
- Chunk nonce = the recording's random 8-byte prefix || u32 chunk index (big-endian).
- Chunk AAD = recording id, chunk index, final flag and the SHA-256 of the header frame.
  Reordering, dropping, truncating or appending chunks, or editing the header, fails to
  decrypt. A recording whose last chunk is not flagged final is incomplete.

Pure framing: AES-GCM runs only in src/vault/envelope.py.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

from src.vault.envelope import (
    GCM_TAG_BYTES,
    VaultIntegrityError,
    aead_open,
    aead_seal,
    new_data_key,
    unwrap_data_key,
    wrap_data_key,
)

MAGIC = b"WXREC\x01"
FORMAT_VERSION = 1
CHUNK_MAX = 64 * 1024
_LEN = struct.Struct(">I")
_MAX_HEADER = 4096


class RecordingIntegrityError(Exception):
    """The encrypted recording failed authentication or is malformed."""


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def _dek_aad(recording_id: uuid.UUID, files_key_version: int) -> bytes:
    return f"wardx-rec-dek|v1|{recording_id}|{files_key_version}".encode()


def _chunk_aad(recording_id: uuid.UUID, index: int, final: bool, header_hash: bytes) -> bytes:
    return f"wardx-rec|v1|{recording_id}|{index}|{1 if final else 0}|".encode() + header_hash


def _nonce(prefix: bytes, index: int) -> bytes:
    return prefix + struct.pack(">I", index)


@dataclass(frozen=True)
class Header:
    recording_id: uuid.UUID
    files_key_version: int
    dek_nonce: bytes
    wrapped_dek: bytes
    nonce_prefix: bytes
    frame: bytes  # the exact header bytes, hashed into every chunk's AAD

    @property
    def digest(self) -> bytes:
        return hashlib.sha256(self.frame).digest()


class RecordingEncryptor:
    """Seals one recording chunk by chunk. Holds its DEK in memory only."""

    def __init__(self, recording_id: uuid.UUID, files_key_version: int, files_key: bytes):
        self.recording_id = recording_id
        self._dek = new_data_key()
        dek_nonce, wrapped = wrap_data_key(
            files_key, self._dek, _dek_aad(recording_id, files_key_version)
        )
        self._prefix = os.urandom(8)
        body = json.dumps(
            {
                "format": FORMAT_VERSION,
                "recording_id": str(recording_id),
                "files_key_version": files_key_version,
                "dek_nonce": _b64(dek_nonce),
                "wrapped_dek": _b64(wrapped),
                "nonce_prefix": _b64(self._prefix),
                "chunk_max": CHUNK_MAX,
            },
            sort_keys=True,
        ).encode()
        self.header = MAGIC + _LEN.pack(len(body)) + body
        self._header_hash = hashlib.sha256(self.header).digest()
        self.index = 0
        self.finished = False

    def chunk(self, plaintext: bytes, *, final: bool = False) -> bytes:
        """The next chunk frame. The final chunk may be empty."""
        if self.finished:
            raise RecordingIntegrityError("recording already finalised")
        if len(plaintext) > CHUNK_MAX:
            raise ValueError("chunk larger than 64 KiB")
        aad = _chunk_aad(self.recording_id, self.index, final, self._header_hash)
        sealed = aead_seal(self._dek, _nonce(self._prefix, self.index), plaintext, aad)
        self.index += 1
        self.finished = final
        return _LEN.pack(len(sealed)) + sealed


def parse_header(data: bytes) -> tuple[Header, int]:
    """The header and the offset where chunk frames start."""
    if not data.startswith(MAGIC) or len(data) < len(MAGIC) + _LEN.size:
        raise RecordingIntegrityError("not a WardX encrypted recording")
    (length,) = _LEN.unpack_from(data, len(MAGIC))
    end = len(MAGIC) + _LEN.size + length
    if length > _MAX_HEADER or end > len(data):
        raise RecordingIntegrityError("recording header is malformed")
    try:
        meta = json.loads(data[len(MAGIC) + _LEN.size : end])
        if meta["format"] != FORMAT_VERSION:
            raise RecordingIntegrityError(f"unknown recording format {meta['format']}")
        header = Header(
            recording_id=uuid.UUID(meta["recording_id"]),
            files_key_version=int(meta["files_key_version"]),
            dek_nonce=base64.b64decode(meta["dek_nonce"]),
            wrapped_dek=base64.b64decode(meta["wrapped_dek"]),
            nonce_prefix=base64.b64decode(meta["nonce_prefix"]),
            frame=data[:end],
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise RecordingIntegrityError("recording header is malformed") from exc
    if len(header.nonce_prefix) != 8:
        raise RecordingIntegrityError("recording header is malformed")
    return header, end


def _frames(data: bytes, offset: int) -> Iterator[bytes]:
    while offset < len(data):
        if offset + _LEN.size > len(data):
            raise RecordingIntegrityError("recording is truncated inside a chunk")
        (length,) = _LEN.unpack_from(data, offset)
        offset += _LEN.size
        if length < GCM_TAG_BYTES or offset + length > len(data):
            raise RecordingIntegrityError("recording is truncated inside a chunk")
        yield data[offset : offset + length]
        offset += length


@dataclass(frozen=True)
class Decrypted:
    plaintext: bytes
    complete: bool  # the last chunk was flagged final
    chunks: int


def decrypt(data: bytes, files_key: bytes, expected_id: uuid.UUID | None = None) -> Decrypted:
    """Decrypt a whole object. Raises RecordingIntegrityError on any authentication
    failure; a recording without a final chunk decrypts as incomplete."""
    header, offset = parse_header(data)
    if expected_id is not None and header.recording_id != expected_id:
        raise RecordingIntegrityError("recording belongs to another session")
    try:
        dek = unwrap_data_key(
            files_key,
            header.dek_nonce,
            header.wrapped_dek,
            _dek_aad(header.recording_id, header.files_key_version),
        )
    except VaultIntegrityError as exc:
        raise RecordingIntegrityError("recording data key failed authentication") from exc
    out: list[bytes] = []
    complete = False
    index = 0
    for frame in _frames(data, offset):
        if complete:
            raise RecordingIntegrityError("data after the final chunk")
        nonce = _nonce(header.nonce_prefix, index)
        try:
            text = aead_open(
                dek, nonce, frame, _chunk_aad(header.recording_id, index, False, header.digest)
            )
        except VaultIntegrityError:
            try:
                text = aead_open(
                    dek, nonce, frame, _chunk_aad(header.recording_id, index, True, header.digest)
                )
            except VaultIntegrityError as exc:
                raise RecordingIntegrityError(
                    f"recording chunk {index} failed authentication"
                ) from exc
            complete = True
        out.append(text)
        index += 1
    return Decrypted(b"".join(out), complete, index)


def files_key_version_of(data: bytes) -> int:
    return parse_header(data)[0].files_key_version
