"""Encrypts a session recording as it is written, spools it, and uploads it (HA_DR.md §5).

Plaintext never touches disk: the asciicast is sealed in chunks of at most 64 KiB
(src/services/session_recordings/recording_format.py). Each chunk is appended to a local spool file
(ciphertext) and uploaded to the object store as ``spool/<session>/<index>`` while the
session runs; a partly filled chunk is sealed every WARDX_RECORDING_FLUSH_SECONDS so a lost
node loses at most that much. At session end the final chunk is sealed and the whole object
is uploaded as ``recordings/<session>.wxrec``; the chunk objects are then removed.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import structlog

from src.services.session_recordings.recording_format import CHUNK_MAX, RecordingEncryptor
from src.services.session_recordings.recording_objects import (
    chunk_key,
    final_key,
    header_key,
    remove_chunks,
)
from src.storage.object_store import ObjectStore

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class StoredRecording:
    key: str
    ciphertext_sha256: str
    ciphertext_bytes: int
    uploaded: bool


class RecordingWriter:
    def __init__(
        self,
        session_id: uuid.UUID,
        *,
        files_key_version: int,
        files_key: bytes,
        store: ObjectStore,
        spool_dir: Path,
        flush_seconds: float = 5.0,
    ) -> None:
        self.session_id = session_id
        self._store = store
        self._enc = RecordingEncryptor(session_id, files_key_version, files_key)
        spool_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.spool_path = spool_dir / f"{session_id}.wxrec"
        fd = os.open(self.spool_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self._fh = os.fdopen(fd, "wb")
        self._fh.write(self._enc.header)
        self._fh.flush()
        self._buffer = bytearray()
        self._queue: asyncio.Queue[tuple[str, bytes] | None] = asyncio.Queue()
        self._queue.put_nowait((header_key(session_id), self._enc.header))
        self._flush_seconds = flush_seconds
        self._uploader = asyncio.create_task(self._upload_loop())
        self._flusher = asyncio.create_task(self._flush_loop())

    # ── Writing (called synchronously from the session pumps) ──

    def write(self, data: bytes) -> None:
        self._buffer += data
        while len(self._buffer) >= CHUNK_MAX:
            self._emit(bytes(self._buffer[:CHUNK_MAX]), final=False)
            del self._buffer[:CHUNK_MAX]

    def _emit(self, plaintext: bytes, *, final: bool) -> None:
        index = self._enc.index
        frame = self._enc.chunk(plaintext, final=final)
        self._fh.write(frame)
        self._fh.flush()
        self._queue.put_nowait((chunk_key(self.session_id, index), frame))

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(self._flush_seconds)
            if self._buffer:
                self._emit(bytes(self._buffer), final=False)
                self._buffer.clear()

    async def _upload_loop(self) -> None:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            key, data = item
            try:
                await self._store.put(key, data)
            except Exception as exc:
                # The spool file has everything; the final upload is what counts.
                logger.warning(
                    "recording_chunk_upload_failed",
                    session_id=str(self.session_id),
                    error=type(exc).__name__,
                )

    # ── Closing ──

    async def close(self) -> StoredRecording:
        self._flusher.cancel()
        self._emit(bytes(self._buffer), final=True)
        self._buffer.clear()
        self._fh.flush()
        os.fsync(self._fh.fileno())
        self._fh.close()
        self._queue.put_nowait(None)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self._uploader, 30)
        data = await asyncio.to_thread(self.spool_path.read_bytes)
        stored = StoredRecording(
            final_key(self.session_id), hashlib.sha256(data).hexdigest(), len(data), False
        )
        try:
            await self._store.put(stored.key, data)
        except Exception as exc:
            # Kept in the spool; the gateway uploads leftovers when it starts again.
            logger.error("recording_upload_failed", session_id=str(self.session_id), error=str(exc))
            return stored
        await remove_chunks(self._store, self.session_id)
        self.spool_path.unlink(missing_ok=True)
        return StoredRecording(stored.key, stored.ciphertext_sha256, stored.ciphertext_bytes, True)

    def abort(self) -> None:
        """Stop without finalising (the process is going away)."""
        self._flusher.cancel()
        self._uploader.cancel()
        with contextlib.suppress(Exception):
            self._fh.close()


async def upload_leftover_spools(store: ObjectStore, spool_dir: Path) -> int:
    """At gateway start: upload spool files whose final upload failed earlier."""
    uploaded = 0

    def _files() -> list[Path]:
        return sorted(spool_dir.glob("*.wxrec")) if spool_dir.is_dir() else []

    for path in await asyncio.to_thread(_files):
        try:
            session_id = uuid.UUID(path.stem)
        except ValueError:
            continue
        key = final_key(session_id)
        try:
            if not await store.exists(key):
                await store.put(key, await asyncio.to_thread(path.read_bytes))
                uploaded += 1
            await remove_chunks(store, session_id)
            path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("recording_leftover_upload_failed", file=path.name, error=str(exc))
    return uploaded
