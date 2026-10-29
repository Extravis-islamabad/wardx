"""Reading gateway sessions, their commands and recordings, and kill requests.

People see their own sessions; SESSIONS_VIEW_ALL sees everyone's. A kill
request only marks the session: the gateway node holding it disconnects it
within a few seconds. Viewing a recording is audited.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from anyio import to_thread

from src.contracts.dto.sessions.gateway_session_dto import (
    GatewaySessionDTO,
    GatewaySessionFilterDTO,
    SessionCommandDTO,
)
from src.core.context import Actor
from src.core.enums import KeyPurpose
from src.core.permissions import SESSIONS_VIEW_ALL
from src.errors.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError
from src.models import utcnow
from src.repositories.sessions.gateway_session_repository import GatewaySessionRepository
from src.services.audit.audit_service import AuditService
from src.services.keys.tenant_key_service import TenantKeyService
from src.services.recordings.recording_format import (
    RecordingIntegrityError,
    decrypt,
    files_key_version_of,
)
from src.storage.object_store import ObjectNotFound, ObjectStore, ObjectStoreError


class RecordingTampered(AppError):
    status_code = 409
    code = "recording_integrity_failed"


class RecordingUnavailable(AppError):
    status_code = 503
    code = "recording_storage_unavailable"


@dataclass(frozen=True)
class RecordingView:
    data: bytes
    verified: bool
    incomplete: bool
    encrypted: bool


class SessionService:
    def __init__(
        self,
        sessions: GatewaySessionRepository,
        audit: AuditService,
        recording_root: Path,
        store: ObjectStore,
        keys: TenantKeyService,
    ) -> None:
        self._sessions = sessions
        self._audit = audit
        self._recording_root = recording_root
        self._store = store
        self._tenant_keys = keys

    async def list(
        self,
        actor: Actor,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        mine: bool = False,
        search: str | None = None,
    ) -> tuple[list[GatewaySessionDTO], int]:
        own = mine or not actor.can(SESSIONS_VIEW_ALL)
        return await self._sessions.list(
            GatewaySessionFilterDTO(
                user_id=actor.id if own else None, status=status, search=search
            ),
            page=page,
            page_size=page_size,
        )

    async def get(self, actor: Actor, session_id: uuid.UUID) -> GatewaySessionDTO:
        row = await self._sessions.get(session_id)
        if row is None:
            raise NotFoundError("Session not found")
        if row.user_id != actor.id and not actor.can(SESSIONS_VIEW_ALL):
            raise ForbiddenError("Not your session")
        return row

    async def commands(self, actor: Actor, session_id: uuid.UUID) -> list[SessionCommandDTO]:
        await self.get(actor, session_id)
        return await self._sessions.commands(session_id)

    async def recording(self, actor: Actor, session_id: uuid.UUID) -> RecordingView:
        """The recording's plaintext and whether it still matches the hash taken when it
        closed. Encrypted recordings come from the object store and are decrypted here;
        any authentication failure refuses the replay (HA_DR.md §5.1)."""
        row = await self.get(actor, session_id)
        if row.recording_key is not None and row.recording_encrypted:
            view = await self._encrypted(row)
        elif row.recording_path is not None:
            view = await self._legacy(row)
        else:
            raise NotFoundError("This session has no recording")
        await self._audit.record(
            actor,
            "session.recording_view",
            object_type="session",
            object_id=row.id,
            details={
                "verified": view.verified,
                "encrypted": view.encrypted,
                "incomplete": view.incomplete,
            },
        )
        await self._sessions.commit()
        return view

    async def _encrypted(self, row: GatewaySessionDTO) -> RecordingView:
        try:
            data = await self._store.get(row.recording_key)
        except ObjectNotFound as exc:
            raise NotFoundError("Recording object is missing from storage") from exc
        except ObjectStoreError as exc:
            raise RecordingUnavailable(f"Recording storage is unavailable: {exc}") from exc
        try:
            version = files_key_version_of(data)
            key = await self._tenant_keys.version(KeyPurpose.FILES, version)
            if key is None:
                raise RecordingIntegrityError(f"files key version {version} is not available")
            out = await to_thread.run_sync(decrypt, data, key, row.id)
        except RecordingIntegrityError as exc:
            raise RecordingTampered(
                f"The recording failed its integrity check and cannot be replayed: {exc}"
            ) from exc
        if not out.complete and not row.recording_incomplete:
            # Recorded as finished, yet the final chunk is gone: truncated after the fact.
            raise RecordingTampered(
                "The recording failed its integrity check and cannot be replayed: "
                "its final chunk is missing (truncated)"
            )
        incomplete = row.recording_incomplete
        verified = (
            not incomplete
            and row.recording_sha256 is not None
            and hashlib.sha256(out.plaintext).hexdigest() == row.recording_sha256
        )
        return RecordingView(out.plaintext, verified, incomplete, True)

    async def _legacy(self, row: GatewaySessionDTO) -> RecordingView:
        """A plaintext recording from before encryption (until `wardx recordings encrypt`)."""
        recording_path = row.recording_path
        root = self._recording_root

        def _read() -> bytes | None:
            # Only serve files inside the recording directory.
            path = Path(recording_path).resolve()
            ok = path.is_relative_to(root.resolve()) and path.is_file()
            return path.read_bytes() if ok else None

        data = await to_thread.run_sync(_read)
        if data is None:
            raise NotFoundError("Recording file is missing")
        verified = bool(row.recording_sha256) and (
            hashlib.sha256(data).hexdigest() == row.recording_sha256
        )
        return RecordingView(data, verified, False, False)

    async def request_terminate(self, actor: Actor, session_id: uuid.UUID) -> GatewaySessionDTO:
        row = await self._sessions.get(session_id, lock=True)
        if row is None:
            raise NotFoundError("Session not found")
        if row.status != "active":
            raise ConflictError(f"Session is already {row.status}")
        if row.terminate_requested_at is None:
            await self._sessions.update(
                row.id, {"terminate_requested_at": utcnow(), "terminate_requested_by": actor.id}
            )
            await self._audit.record(
                actor,
                "session.terminate",
                object_type="session",
                object_id=row.id,
                details={"user_id": str(row.user_id), "target": row.target_name},
            )
        await self._sessions.commit()
        return await self._sessions.get(row.id)
