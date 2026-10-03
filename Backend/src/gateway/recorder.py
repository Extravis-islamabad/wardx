"""Session recording in asciicast v2 (asciinema), hashed while it is written.

The SHA-256 is stored on the session row and in the audit chain's
``session.end`` event, so a recording edited later no longer matches.
"""

from __future__ import annotations

import codecs
import hashlib
import json
import os
import time
from pathlib import Path


class AsciicastRecorder:
    def __init__(
        self, path: Path, *, width: int, height: int, term: str | None, title: str
    ) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self.path = path
        self._fh = os.fdopen(fd, "wb")
        self._hash = hashlib.sha256()
        self._size = 0
        self._start = time.monotonic()
        # Output arrives in arbitrary chunks; keep split UTF-8 sequences intact.
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        header = {
            "version": 2,
            "width": max(width, 1),
            "height": max(height, 1),
            "timestamp": int(time.time()),
            "title": title,
            "env": {"TERM": term or "unknown"},
        }
        self._write(header)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._start

    def _write(self, obj: object) -> None:
        line = (json.dumps(obj, ensure_ascii=False) + "\n").encode()
        self._fh.write(line)
        self._hash.update(line)
        self._size += len(line)

    def output(self, data: bytes) -> None:
        text = self._decoder.decode(data)
        if text:
            self._write([round(self.elapsed, 6), "o", text])

    def marker(self, label: str) -> None:
        self._write([round(self.elapsed, 6), "m", label])

    def resize(self, width: int, height: int) -> None:
        self._write([round(self.elapsed, 6), "r", f"{width}x{height}"])

    def close(self) -> tuple[str, int]:
        tail = self._decoder.decode(b"", final=True)
        if tail:
            self._write([round(self.elapsed, 6), "o", tail])
        self._fh.close()
        return self._hash.hexdigest(), self._size


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()
