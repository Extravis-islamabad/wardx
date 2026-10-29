"""Local-filesystem object store: single-node installs and the plain test run."""

from __future__ import annotations

import os
from pathlib import Path

from anyio import to_thread

from src.storage.object_store import ObjectNotFound, check_key


class LocalObjectStore:
    name = "local"

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        return self.root / check_key(key)

    async def put(self, key: str, data: bytes) -> None:
        path = self._path(key)

        def _write() -> None:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".part")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)

        await to_thread.run_sync(_write)

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return await to_thread.run_sync(path.read_bytes)
        except FileNotFoundError as exc:
            raise ObjectNotFound(key) from exc

    async def list(self, prefix: str) -> list[str]:
        base = self.root / prefix.rstrip("/") if prefix else self.root

        def _walk() -> list[str]:
            if not base.is_dir():
                return []
            return sorted(
                p.relative_to(self.root).as_posix()
                for p in base.rglob("*")
                if p.is_file() and not p.name.endswith(".part")
            )

        return await to_thread.run_sync(_walk)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await to_thread.run_sync(lambda: path.unlink(missing_ok=True))

    async def exists(self, key: str) -> bool:
        return await to_thread.run_sync(self._path(key).is_file)
