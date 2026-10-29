"""`wardx recordings encrypt`: migrate legacy plaintext recordings (HA_DR.md §5.1).

1. Encrypt each plaintext recording into a new encrypted object.
2. Read it back from the store, decrypt it and compare the SHA-256 with the stored
   ``recording_sha256``; only a match marks the session migrated. A mismatch (or a
   recording without a stored hash) leaves the original untouched, removes the unverified
   copy and is reported.
3. Originals are kept. A separate run with ``--remove-verified-originals`` deletes them,
   only for migrated recordings, and only after verifying the encrypted copy again.
4. Every outcome is audited per recording (the session's safe is resolved from it).

Resumable: each recording is its own unit of work, and a run only picks recordings not yet
migrated, so an interrupted run continues where it stopped.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from anyio import to_thread

from src.contracts.dto.sessions.gateway_session_dto import GatewaySessionDTO
from src.core.context import SYSTEM_ACTOR
from src.core.enums import KeyPurpose
from src.models import utcnow
from src.repositories.sessions.gateway_session_repository import GatewaySessionRepository
from src.services.audit.audit_service import AuditService
from src.services.keys.tenant_key_service import TenantKeyService
from src.services.session_recordings.recording_format import (
    CHUNK_MAX,
    RecordingEncryptor,
    RecordingIntegrityError,
    decrypt,
    files_key_version_of,
)
from src.services.session_recordings.recording_objects import final_key
from src.storage.object_store import ObjectStore

_BATCH = 50


@dataclass
class MigrationReport:
    migrated: list[uuid.UUID] = field(default_factory=list)
    removed: list[uuid.UUID] = field(default_factory=list)
    failed: list[tuple[uuid.UUID, str]] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [f"migrated  {sid}" for sid in self.migrated]
        out += [f"removed   {sid} (original)" for sid in self.removed]
        out += [f"FAILED    {sid}: {why}" for sid, why in self.failed]
        out.append(
            f"{len(self.migrated)} migrated, {len(self.removed)} originals removed, "
            f"{len(self.failed)} failed"
        )
        return out


def encrypt_plaintext(session_id: uuid.UUID, version: int, key: bytes, plain: bytes) -> bytes:
    enc = RecordingEncryptor(session_id, version, key)
    parts = [enc.header]
    chunks = [plain[i : i + CHUNK_MAX] for i in range(0, len(plain), CHUNK_MAX)] or [b""]
    for i, chunk in enumerate(chunks):
        parts.append(enc.chunk(chunk, final=i == len(chunks) - 1))
    return b"".join(parts)


class RecordingMigrationService:
    def __init__(
        self,
        sessions: GatewaySessionRepository,
        audit: AuditService,
        keys: TenantKeyService,
        store: ObjectStore,
        recording_root: Path,
    ) -> None:
        self._sessions = sessions
        self._audit = audit
        self._tenant_keys = keys
        self._store = store
        self._root = recording_root.resolve()

    def _inside_root(self, path: str) -> Path | None:
        p = Path(path).resolve()
        return p if p.is_relative_to(self._root) else None

    async def _read_original(self, row: GatewaySessionDTO) -> bytes:
        path = self._inside_root(row.recording_path or "")
        if path is None:
            raise FileNotFoundError("outside the recording directory")
        return await to_thread.run_sync(path.read_bytes)

    async def _verified_copy(self, row: GatewaySessionDTO, key: str) -> str:
        """Read the stored copy back and decrypt it; its ciphertext SHA-256 if it matches."""
        data = await self._store.get(key)
        files_key = await self._tenant_keys.version(KeyPurpose.FILES, files_key_version_of(data))
        if files_key is None:
            raise RecordingIntegrityError("files key version not available")
        out = await to_thread.run_sync(decrypt, data, files_key, row.id)
        if not out.complete:
            raise RecordingIntegrityError("encrypted copy has no final chunk")
        if hashlib.sha256(out.plaintext).hexdigest() != row.recording_sha256:
            raise RecordingIntegrityError("SHA-256 does not match recording_sha256")
        return hashlib.sha256(data).hexdigest()

    async def _audit_one(self, action: str, row: GatewaySessionDTO, ok: bool, **details) -> None:
        await self._audit.record(
            SYSTEM_ACTOR,
            action,
            object_type="session",
            object_id=row.id,
            outcome="success" if ok else "failure",
            details=details,
        )

    async def encrypt_all(self, *, limit: int | None = None) -> MigrationReport:
        report = MigrationReport()
        after: uuid.UUID | None = None
        while limit is None or len(report.migrated) + len(report.failed) < limit:
            batch = await self._sessions.plaintext_recordings(after, _BATCH)
            await self._sessions.rollback()
            if not batch:
                break
            for row in batch:
                after = row.id
                await self.encrypt_one(row, report)
                if limit is not None and len(report.migrated) + len(report.failed) >= limit:
                    break
        return report

    async def encrypt_one(self, row: GatewaySessionDTO, report: MigrationReport) -> None:
        key = final_key(row.id)
        try:
            if not row.recording_sha256:
                raise RecordingIntegrityError("no recording_sha256 stored: cannot verify")
            plain = await self._read_original(row)
            version, files_key = await self._tenant_keys.active(KeyPurpose.FILES)
            data = await to_thread.run_sync(encrypt_plaintext, row.id, version, files_key, plain)
            await self._store.put(key, data)
            cipher_sha = await self._verified_copy(row, key)
        except (RecordingIntegrityError, OSError) as exc:
            reason = str(exc) or type(exc).__name__
            if not isinstance(exc, FileNotFoundError):
                try:
                    await self._store.delete(key)  # never leave an unverified copy behind
                except Exception:  # noqa: S110 - best effort; it is not referenced
                    pass
            await self._audit_one(
                "session.recording_encrypt_failed", row, False, reason=reason, original_kept=True
            )
            await self._sessions.commit()
            report.failed.append((row.id, reason))
            return
        await self._sessions.update(
            row.id,
            {
                "recording_key": key,
                "recording_encrypted": True,
                "recording_ciphertext_sha256": cipher_sha,
                "recording_migrated_at": utcnow(),
            },
        )
        await self._audit_one(
            "session.recording_encrypted",
            row,
            True,
            recording_key=key,
            recording_sha256=row.recording_sha256,
            ciphertext_sha256=cipher_sha,
            original_kept=True,
        )
        await self._sessions.commit()
        report.migrated.append(row.id)

    async def remove_verified_originals(self, *, limit: int | None = None) -> MigrationReport:
        report = MigrationReport()
        after: uuid.UUID | None = None
        while limit is None or len(report.removed) + len(report.failed) < limit:
            batch = await self._sessions.migrated_with_originals(after, _BATCH)
            await self._sessions.rollback()
            if not batch:
                break
            for row in batch:
                after = row.id
                await self._remove_one(row, report)
        return report

    async def _remove_one(self, row: GatewaySessionDTO, report: MigrationReport) -> None:
        try:
            # Verify the encrypted copy again right before the original goes.
            await self._verified_copy(row, row.recording_key or final_key(row.id))
            path = self._inside_root(row.recording_path or "")
            if path is None:
                raise FileNotFoundError("outside the recording directory")
            await to_thread.run_sync(lambda: path.unlink(missing_ok=True))
        except Exception as exc:
            reason = str(exc) or type(exc).__name__
            await self._audit_one(
                "session.recording_original_remove_failed", row, False, reason=reason
            )
            await self._sessions.commit()
            report.failed.append((row.id, reason))
            return
        await self._sessions.update(
            row.id, {"recording_original_removed_at": utcnow(), "recording_path": None}
        )
        await self._audit_one(
            "session.recording_original_removed", row, True, recording_key=row.recording_key
        )
        await self._sessions.commit()
        report.removed.append(row.id)
