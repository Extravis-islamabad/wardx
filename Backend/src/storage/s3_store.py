"""S3-compatible object store (MinIO on-prem, S3 in the cloud) through the minio client.

The client is synchronous; every call runs in a worker thread. The bucket is created on
first use if it does not exist. Credentials come from WARDX_S3_ACCESS_KEY and
WARDX_S3_SECRET_KEY (or WARDX_S3_SECRET_KEY_FILE) and are never logged.
"""

from __future__ import annotations

import io
from pathlib import Path

from anyio import to_thread
from minio import Minio
from minio.error import S3Error

from src.core.config import Settings
from src.storage.object_store import ObjectNotFound, ObjectStoreError, check_key


class S3ObjectStore:
    name = "s3"

    def __init__(self, client: Minio, bucket: str) -> None:
        self._client = client
        self.bucket = bucket
        self._bucket_ready = False

    @classmethod
    def from_settings(cls, settings: Settings) -> S3ObjectStore:
        if not settings.s3_endpoint:
            raise ObjectStoreError("WARDX_S3_ENDPOINT is required for the s3 recording store")
        secret = settings.s3_secret_key
        if settings.s3_secret_key_file:
            secret = Path(settings.s3_secret_key_file).read_text().strip()
        client = Minio(
            settings.s3_endpoint,
            access_key=settings.s3_access_key or None,
            secret_key=secret or None,
            secure=settings.s3_secure,
            region=settings.s3_region or None,
        )
        return cls(client, settings.s3_bucket)

    async def _call(self, fn, *args, **kwargs):
        def run():
            if not self._bucket_ready:
                if not self._client.bucket_exists(self.bucket):
                    self._client.make_bucket(self.bucket)
                self._bucket_ready = True
            return fn(*args, **kwargs)

        try:
            return await to_thread.run_sync(run)
        except S3Error as exc:
            if exc.code in ("NoSuchKey", "NoSuchObject"):
                raise ObjectNotFound(str(args[0]) if args else "") from exc
            raise ObjectStoreError(f"object store error: {exc.code}") from exc
        except (OSError, ValueError) as exc:
            raise ObjectStoreError(f"object store unreachable: {type(exc).__name__}") from exc

    async def put(self, key: str, data: bytes) -> None:
        check_key(key)
        await self._call(
            lambda: self._client.put_object(
                self.bucket,
                key,
                io.BytesIO(data),
                len(data),
                content_type="application/octet-stream",
            )
        )

    async def get(self, key: str) -> bytes:
        check_key(key)

        def fetch(k: str) -> bytes:
            resp = self._client.get_object(self.bucket, k)
            try:
                return resp.read()
            finally:
                resp.close()
                resp.release_conn()

        return await self._call(fetch, key)

    async def list(self, prefix: str) -> list[str]:
        return await self._call(
            lambda: sorted(
                o.object_name
                for o in self._client.list_objects(self.bucket, prefix=prefix, recursive=True)
            )
        )

    async def delete(self, key: str) -> None:
        check_key(key)
        await self._call(lambda: self._client.remove_object(self.bucket, key))

    async def exists(self, key: str) -> bool:
        check_key(key)
        try:
            await self._call(self._client.stat_object, self.bucket, key)
        except ObjectNotFound:
            return False
        return True
