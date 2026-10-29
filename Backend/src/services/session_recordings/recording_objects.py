"""Where encrypted recordings live in the object store, and salvaging a cut-off one.

- ``recordings/<session>.wxrec``: the finished object (header and every chunk).
- ``spool/<session>/header`` and ``spool/<session>/<index>``: uploaded while the session
  runs, removed once the finished object is stored.

A session cut off by a lost gateway node has no finished object. Salvage joins the header
and the contiguous chunks uploaded so far into ``recordings/<session>.wxrec``, which
decrypts up to the last uploaded chunk and is marked incomplete (HA_DR.md §5.1).
"""

from __future__ import annotations

import contextlib
import hashlib
import uuid
from typing import Any

from src.storage.object_store import ObjectStore


def final_key(session_id: uuid.UUID) -> str:
    return f"recordings/{session_id}.wxrec"


def spool_prefix(session_id: uuid.UUID) -> str:
    return f"spool/{session_id}/"


def header_key(session_id: uuid.UUID) -> str:
    return f"{spool_prefix(session_id)}header"


def chunk_key(session_id: uuid.UUID, index: int) -> str:
    return f"{spool_prefix(session_id)}{index:08d}"


async def remove_chunks(store: ObjectStore, session_id: uuid.UUID) -> None:
    for key in await store.list(spool_prefix(session_id)):
        with contextlib.suppress(Exception):
            await store.delete(key)


async def salvage(store: ObjectStore, session_id: uuid.UUID) -> dict[str, Any]:
    """Session fields for a cut-off recording; {} when nothing was uploaded."""
    key = final_key(session_id)
    if await store.exists(key):
        data = await store.get(key)
    else:
        keys = set(await store.list(spool_prefix(session_id)))
        if header_key(session_id) not in keys:
            return {}
        parts = [await store.get(header_key(session_id))]
        index = 0
        while chunk_key(session_id, index) in keys:
            parts.append(await store.get(chunk_key(session_id, index)))
            index += 1
        data = b"".join(parts)
        await store.put(key, data)
        await remove_chunks(store, session_id)
    return {
        "recording_key": key,
        "recording_encrypted": True,
        "recording_incomplete": True,
        "recording_ciphertext_sha256": hashlib.sha256(data).hexdigest(),
        "recording_sha256": None,
    }
