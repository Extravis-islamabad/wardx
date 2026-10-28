"""The gateway's session records: opening, commands typed, closing, and recovery.

Each method is one unit of work with its audit events. The gateway decides
what to do (src/gateway/broker.py); this service only records it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from src.contracts.dto.inventory.account_dto import AccountDTO
from src.contracts.dto.inventory.target_dto import TargetDTO
from src.core.context import SYSTEM_ACTOR, Actor
from src.models import utcnow
from src.repositories.sessions.gateway_session_repository import GatewaySessionRepository
from src.services.audit.audit_service import AuditService


class GatewaySessionService:
    def __init__(self, sessions: GatewaySessionRepository, audit: AuditService) -> None:
        self._sessions = sessions
        self._audit = audit

    async def start(
        self,
        actor: Actor,
        *,
        checkout_id: uuid.UUID,
        account: AccountDTO,
        target: TargetDTO,
        mode: str,
        command: str | None,
        node: str,
    ) -> uuid.UUID:
        """Record a session starting, with the credential injected into it."""
        session_id = await self._sessions.create(
            {
                "checkout_id": checkout_id,
                "user_id": actor.id,
                "account_id": account.id,
                "target_id": target.id,
                "account_username": account.username,
                "target_name": target.name,
                "target_address": target.address,
                "protocol": target.protocol,
                "mode": mode,
                "exec_command": command,
                "client_ip": actor.source_ip,
                "gateway_node": node,
                "status": "active",
                "started_at": utcnow(),
            }
        )
        await self._audit.record(
            actor,
            "session.start",
            object_type="session",
            object_id=session_id,
            details={
                "account_id": str(account.id),
                "target": target.name,
                "mode": mode,
                "command": command,
                "checkout_id": str(checkout_id),
                "gateway": node,
            },
        )
        await self._audit.record(
            actor,
            "secret.inject",
            object_type="session",
            object_id=session_id,
            details={"account_id": str(account.id), "version": account.secret_version},
        )
        await self._sessions.commit()
        return session_id

    async def record_command(
        self,
        actor: Actor,
        session_id: uuid.UUID,
        *,
        offset: float,
        command: str,
        blocked_rule: uuid.UUID | None,
        blocked: bool,
        edited: bool,
    ) -> None:
        await self._sessions.add_command(
            {
                "session_id": session_id,
                "occurred_at": utcnow(),
                "offset_seconds": offset,
                "command": command + (" ⟨edited⟩" if edited else ""),
                "verdict": "blocked" if blocked else "allowed",
                "rule_id": blocked_rule,
            },
            blocked=blocked,
        )
        if blocked:
            await self._audit.record(
                actor,
                "session.command_blocked",
                object_type="session",
                object_id=session_id,
                outcome="failure",
                details={"command": command, "rule_id": str(blocked_rule)},
            )
        await self._sessions.commit()

    async def close_state(
        self, session_ids: list[uuid.UUID]
    ) -> list[tuple[uuid.UUID, datetime | None, str | None, str | None, datetime | None]]:
        return await self._sessions.close_state(session_ids)

    async def finish(
        self,
        actor: Actor,
        session_id: uuid.UUID,
        *,
        status: str,
        reason: str,
        recording_path: str | None,
        recording_sha256: str | None,
        recording_bytes: int | None,
        bytes_from_target: int,
        bytes_from_user: int,
    ) -> None:
        await self._sessions.finish_active(
            session_id,
            {
                "status": status,
                "ended_at": utcnow(),
                "close_reason": reason,
                "recording_path": recording_path,
                "recording_sha256": recording_sha256,
                "recording_bytes": recording_bytes,
                "bytes_from_target": bytes_from_target,
                "bytes_from_user": bytes_from_user,
            },
        )
        await self._audit.record(
            actor,
            "session.end",
            object_type="session",
            object_id=session_id,
            outcome="success" if status in ("closed", "terminated") else "failure",
            details={
                "status": status,
                "reason": reason,
                "recording_sha256": recording_sha256,
                "bytes_from_target": bytes_from_target,
            },
        )
        await self._sessions.commit()

    async def recover_orphans(self, node: str) -> int:
        """Fail sessions left 'active' by a previous run of this gateway node."""
        ids = await self._sessions.fail_active_on_node(node, utcnow())
        for sid in ids:
            await self._audit.record(
                SYSTEM_ACTOR,
                "session.end",
                object_type="session",
                object_id=sid,
                outcome="failure",
                details={"status": "failed", "reason": "Gateway restarted"},
            )
        await self._sessions.commit()
        return len(ids)
