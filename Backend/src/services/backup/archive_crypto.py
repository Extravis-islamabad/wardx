"""Encrypted backup archives (HA_DR.md §7): streaming AES-256-GCM, DEK wrapped by the KEK.

    file   = b"WXBAK" 0x01 | u32 length | JSON {format, name, kek_id, wrap_nonce,
             wrapped_dek, nonce_prefix} | chunk frames (u32 length | ciphertext+tag)

- A fresh DEK per archive, wrapped by the key provider (the install's KEK, escrowed
  separately, §6), so a restore needs only the escrowed KEK, never the database being
  restored. Keys never go into an archive.
- Chunks of at most 64 KiB; nonce = 8-byte random prefix || u32 index; AAD = archive name,
  index, final flag and the header's SHA-256. Reordered, dropped, truncated, appended or
  edited data fails; decryption refuses an archive without its final chunk.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
from typing import BinaryIO

from src.keys.provider import KeyIntegrityError, KeyProvider, KeyProviderError, WrappedKey
from src.vault.envelope import VaultIntegrityError, aead_open, aead_seal, new_data_key

MAGIC = b"WXBAK\x01"
CHUNK = 64 * 1024
_LEN = struct.Struct(">I")


class ArchiveIntegrityError(Exception):
    """The archive failed authentication or is malformed."""


def _dek_aad(name: str) -> bytes:
    return f"wardx-backup-dek|v1|{name}".encode()


def _aad(name: str, index: int, final: bool, header_hash: bytes) -> bytes:
    return f"wardx-backup|v1|{name}|{index}|{1 if final else 0}|".encode() + header_hash


async def encrypt_stream(provider: KeyProvider, name: str, src: BinaryIO, dst: BinaryIO) -> int:
    """Encrypt ``src`` into ``dst``; returns the plaintext byte count."""
    dek = new_data_key()
    wrapped = await provider.wrap(dek, _dek_aad(name))
    prefix = os.urandom(8)
    body = json.dumps(
        {
            "format": 1,
            "name": name,
            "kek_id": wrapped.key_id,
            "wrap_nonce": base64.b64encode(wrapped.nonce).decode(),
            "wrapped_dek": base64.b64encode(wrapped.blob).decode(),
            "nonce_prefix": base64.b64encode(prefix).decode(),
        },
        sort_keys=True,
    ).encode()
    header = MAGIC + _LEN.pack(len(body)) + body
    header_hash = hashlib.sha256(header).digest()
    dst.write(header)
    total, index = 0, 0
    current = src.read(CHUNK)
    while True:
        following = src.read(CHUNK) if current else b""
        final = not following
        sealed = aead_seal(
            dek, prefix + struct.pack(">I", index), current, _aad(name, index, final, header_hash)
        )
        dst.write(_LEN.pack(len(sealed)) + sealed)
        total += len(current)
        index += 1
        if final:
            return total
        current = following


async def decrypt_stream(provider: KeyProvider, src: BinaryIO, dst: BinaryIO) -> str:
    """Decrypt ``src`` into ``dst``; returns the archive name. Raises on any tampering."""
    head = src.read(len(MAGIC) + _LEN.size)
    if not head.startswith(MAGIC) or len(head) < len(MAGIC) + _LEN.size:
        raise ArchiveIntegrityError("not a WardX encrypted backup archive")
    (length,) = _LEN.unpack_from(head, len(MAGIC))
    if length > 4096:
        raise ArchiveIntegrityError("archive header is malformed")
    body = src.read(length)
    try:
        meta = json.loads(body)
        name = str(meta["name"])
        wrapped = WrappedKey(
            meta["kek_id"],
            base64.b64decode(meta["wrap_nonce"]),
            base64.b64decode(meta["wrapped_dek"]),
        )
        prefix = base64.b64decode(meta["nonce_prefix"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ArchiveIntegrityError("archive header is malformed") from exc
    header_hash = hashlib.sha256(head + body).digest()
    try:
        dek = await provider.unwrap(wrapped, _dek_aad(name))
    except (KeyIntegrityError, KeyProviderError) as exc:
        raise ArchiveIntegrityError(
            f"archive data key does not open with this node's KEKs (wrapped by {wrapped.key_id})"
        ) from exc
    index, finished = 0, False
    while True:
        raw = src.read(_LEN.size)
        if not raw:
            break
        if finished:
            raise ArchiveIntegrityError("data after the final chunk")
        if len(raw) < _LEN.size:
            raise ArchiveIntegrityError("archive is truncated")
        (size,) = _LEN.unpack(raw)
        sealed = src.read(size)
        if len(sealed) != size:
            raise ArchiveIntegrityError("archive is truncated")
        nonce = prefix + struct.pack(">I", index)
        try:
            plain = aead_open(dek, nonce, sealed, _aad(name, index, False, header_hash))
        except VaultIntegrityError:
            try:
                plain = aead_open(dek, nonce, sealed, _aad(name, index, True, header_hash))
            except VaultIntegrityError as exc:
                raise ArchiveIntegrityError(f"archive chunk {index} failed authentication") from exc
            finished = True
        dst.write(plain)
        index += 1
    if not finished:
        raise ArchiveIntegrityError("archive is truncated (no final chunk)")
    return name
