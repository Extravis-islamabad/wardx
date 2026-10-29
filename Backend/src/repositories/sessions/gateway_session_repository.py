"""Gateway sessions (access.sessions) and the commands typed in them."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select, update

from src.contracts.dto.sessions.gateway_session_dto import (
    GatewaySessionDTO,
    GatewaySessionFilterDTO,
    SessionCommandDTO,
)
from src.models import Checkout, GatewaySession, SessionCommand
from src.repositories.base import BaseRepository


def _to_dto(row: GatewaySession) -> GatewaySessionDTO:
    return GatewaySessionDTO(
        id=row.id,
        checkout_id=row.checkout_id,
        user_id=row.user_id,
        username=row.user.username,
        account_id=row.account_id,
        account_username=row.account_username,
        target_id=row.target_id,
        target_name=row.target_name,
        target_address=row.target_address,
        protocol=row.protocol,
        mode=row.mode,
        exec_command=row.exec_command,
        client_ip=row.client_ip,
        gateway_node=row.gateway_node,
        status=row.status,
        started_at=row.started_at,
        ended_at=row.ended_at,
        close_reason=row.close_reason,
        terminate_requested_at=row.terminate_requested_at,
        recording_path=row.recording_path,
        recording_sha256=row.recording_sha256,
        recording_bytes=row.recording_bytes,
        bytes_from_target=row.bytes_from_target,
        commands_count=row.commands_count,
        blocked_count=row.blocked_count,
        recording_key=row.recording_key,
        recording_encrypted=row.recording_encrypted,
        recording_incomplete=row.recording_incomplete,
        recording_ciphertext_sha256=row.recording_ciphertext_sha256,
        recording_migrated_at=row.recording_migrated_at,
        recording_original_removed_at=row.recording_original_removed_at,
    )


def _command_dto(row: SessionCommand) -> SessionCommandDTO:
    return SessionCommandDTO(
        id=row.id,
        occurred_at=row.occurred_at,
        offset_seconds=row.offset_seconds,
        command=row.command,
        verdict=row.verdict,
        rule_id=row.rule_id,
    )


class GatewaySessionRepository(BaseRepository):
    async def list(
        self, filters: GatewaySessionFilterDTO, *, page: int, page_size: int
    ) -> tuple[list[GatewaySessionDTO], int]:
        conditions = []
        if filters.user_id is not None:
            conditions.append(GatewaySession.user_id == filters.user_id)
        if filters.status:
            conditions.append(GatewaySession.status == filters.status)
        if filters.search:
            like = f"%{filters.search.lower()}%"
            conditions.append(
                or_(
                    func.lower(GatewaySession.target_name).like(like),
                    func.lower(GatewaySession.account_username).like(like),
                    func.lower(GatewaySession.target_address).like(like),
                )
            )
        total = (
            await self._session.execute(
                select(func.count()).select_from(GatewaySession).where(*conditions)
            )
        ).scalar_one()
        rows = (
            (
                await self._session.execute(
                    select(GatewaySession)
                    .where(*conditions)
                    .order_by(GatewaySession.started_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            .unique()
            .scalars()
            .all()
        )
        return [_to_dto(r) for r in rows], total

    async def get(self, session_id: uuid.UUID, *, lock: bool = False) -> GatewaySessionDTO | None:
        stmt = select(GatewaySession).where(GatewaySession.id == session_id)
        if lock:
            stmt = stmt.with_for_update(of=GatewaySession)
        row = (await self._session.execute(stmt)).unique().scalar_one_or_none()
        return _to_dto(row) if row else None

    async def update(self, session_id: uuid.UUID, changes: dict[str, Any]) -> None:
        row = await self._session.get(GatewaySession, session_id)
        for field, value in changes.items():
            setattr(row, field, value)
        await self._session.flush()

    async def commands(self, session_id: uuid.UUID) -> list[SessionCommandDTO]:
        rows = await self._session.scalars(
            select(SessionCommand)
            .where(SessionCommand.session_id == session_id)
            .order_by(SessionCommand.id)
        )
        return [_command_dto(r) for r in rows]

    # ── Gateway side ──

    async def create(self, values: dict[str, Any]) -> uuid.UUID:
        row = GatewaySession(**values)
        self._session.add(row)
        await self._session.flush()
        return row.id

    async def add_command(self, values: dict[str, Any], *, blocked: bool) -> None:
        """Log a command and bump the session's command (and blocked) counters."""
        self._session.add(SessionCommand(**values))
        counters = {"commands_count": GatewaySession.commands_count + 1}
        if blocked:
            counters["blocked_count"] = GatewaySession.blocked_count + 1
        await self._session.execute(
            update(GatewaySession)
            .where(GatewaySession.id == values["session_id"])
            .values(**counters)
        )

    async def close_state(
        self, session_ids: list[uuid.UUID]
    ) -> list[tuple[uuid.UUID, datetime | None, str | None, str | None, datetime | None]]:
        """Per session: (id, terminate_requested_at, close_reason, check-out status,
        check-out expires_at); the check-out columns are None without a check-out."""
        rows = await self._session.execute(
            select(
                GatewaySession.id,
                GatewaySession.terminate_requested_at,
                GatewaySession.close_reason,
                Checkout.status,
                Checkout.expires_at,
            )
            .join(Checkout, Checkout.id == GatewaySession.checkout_id, isouter=True)
            .where(GatewaySession.id.in_(session_ids))
        )
        return [tuple(r) for r in rows.all()]

    # ── Recording migration (`wardx recordings encrypt`) ──

    async def plaintext_recordings(
        self, after: uuid.UUID | None, limit: int
    ) -> list[GatewaySessionDTO]:
        """Finished sessions with a legacy plaintext recording not yet migrated, by id."""
        stmt = select(GatewaySession).where(
            GatewaySession.status != "active",
            GatewaySession.recording_path.is_not(None),
            GatewaySession.recording_migrated_at.is_(None),
            GatewaySession.recording_encrypted.is_(False),
        )
        if after is not None:
            stmt = stmt.where(GatewaySession.id > after)
        rows = await self._session.execute(stmt.order_by(GatewaySession.id).limit(limit))
        return [_to_dto(r) for r in rows.unique().scalars()]

    async def migrated_with_originals(
        self, after: uuid.UUID | None, limit: int
    ) -> list[GatewaySessionDTO]:
        stmt = select(GatewaySession).where(
            GatewaySession.recording_migrated_at.is_not(None),
            GatewaySession.recording_original_removed_at.is_(None),
            GatewaySession.recording_path.is_not(None),
        )
        if after is not None:
            stmt = stmt.where(GatewaySession.id > after)
        rows = await self._session.execute(stmt.order_by(GatewaySession.id).limit(limit))
        return [_to_dto(r) for r in rows.unique().scalars()]

    async def end_if_active(self, session_id: uuid.UUID, values: dict[str, Any]) -> bool:
        """Close the session with ``values`` if it is still active; whether it was."""
        rows = await self._session.execute(
            update(GatewaySession)
            .where(GatewaySession.id == session_id, GatewaySession.status == "active")
            .values(**values)
            .returning(GatewaySession.id)
        )
        return rows.first() is not None

    async def request_kill_for_user(
        self, user_id: uuid.UUID, now: datetime, reason: str
    ) -> list[uuid.UUID]:
        """Ask the gateway to end the user's live sessions (not already being killed)."""
        return list(
            (
                await self._session.execute(
                    update(GatewaySession)
                    .where(
                        GatewaySession.user_id == user_id,
                        GatewaySession.status == "active",
                        GatewaySession.terminate_requested_at.is_(None),
                    )
                    .values(terminate_requested_at=now, close_reason=reason)
                    .returning(GatewaySession.id)
                )
            )
            .scalars()
            .all()
        )
