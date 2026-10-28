"""Reading gateway sessions, their commands and recordings, and kill requests.

People see their own sessions; SESSIONS_VIEW_ALL sees everyone's. A kill
request only marks the session: the gateway node holding it disconnects it
within a few seconds. Viewing a recording is audited.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from anyio import to_thread

from src.contracts.dto.sessions.gateway_session_dto import (
    GatewaySessionDTO,
    GatewaySessionFilterDTO,
    SessionCommandDTO,
)
from src.core.context import Actor
from src.core.permissions import SESSIONS_VIEW_ALL
from src.errors.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.gateway.recorder import file_sha256
from src.models import utcnow
from src.repositories.sessions.gateway_session_repository import GatewaySessionRepository
from src.services.audit.audit_service import AuditService


class SessionService:
    def __init__(
        self, sessions: GatewaySessionRepository, audit: AuditService, recording_root: Path
    ) -> None:
        self._sessions = sessions
        self._audit = audit
        self._recording_root = recording_root

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

    async def recording(self, actor: Actor, session_id: uuid.UUID) -> tuple[Path, bool]:
        """The recording file and whether it still matches the hash taken when it closed."""
        row = await self.get(actor, session_id)
        if row.recording_path is None:
            raise NotFoundError("This session has no recording")
        recording_path = row.recording_path
        root = self._recording_root

        def _locate() -> Path | None:
            # Only serve files inside the recording directory.
            path = Path(recording_path).resolve()
            ok = path.is_relative_to(root.resolve()) and path.is_file()
            return path if ok else None

        path = await to_thread.run_sync(_locate)
        if path is None:
            raise NotFoundError("Recording file is missing")
        verified = False
        if row.recording_sha256:
            verified = await to_thread.run_sync(file_sha256, path) == row.recording_sha256
        await self._audit.record(
            actor,
            "session.recording_view",
            object_type="session",
            object_id=row.id,
            details={"verified": verified},
        )
        await self._sessions.commit()
        return path, verified

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
