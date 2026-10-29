"""The object store interface (HA_DR.md §5) and the configured store.

Recordings are written as ciphertext only (§5.1). Keys are relative paths made of
``[A-Za-z0-9._-]`` segments separated by ``/``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

from src.core.config import Settings

_KEY = re.compile(r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$")


class ObjectStoreError(Exception):
    """The store is unreachable or refused the request."""


class ObjectNotFound(ObjectStoreError):
    """No object under that key."""


def check_key(key: str) -> str:
    if not _KEY.match(key) or any(part in (".", "..") for part in key.split("/")):
        raise ValueError(f"invalid object key {key!r}")
    return key


class ObjectStore(Protocol):
    name: str

    async def put(self, key: str, data: bytes) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def list(self, prefix: str) -> list[str]:
        """Keys under ``prefix``, sorted."""
        ...

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...


def build_object_store(settings: Settings) -> ObjectStore:
    if settings.recording_store == "s3":
        from src.storage.s3_store import S3ObjectStore

        return S3ObjectStore.from_settings(settings)
    from src.storage.local_store import LocalObjectStore

    root = settings.recording_store_dir or str(Path(settings.recording_dir) / "store")
    return LocalObjectStore(Path(root))
