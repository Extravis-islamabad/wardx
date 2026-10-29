"""Gateway nodes: heartbeats, the shared host key check, and ending a lost node's sessions.

HA_DR.md §5: a live SSH session cannot move to another node. When a node's heartbeat is
older than WARDX_GATEWAY_LOST_SECONDS, the scheduler leader ends its sessions as
``terminated`` / "Gateway node lost" (audited, with the session's safe), keeps the partial
recording marked incomplete, and closes the check-outs the sessions opened through the
same check-in a normal session end uses, so after-use rotation and exclusivity hold.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import structlog

from src.core.context import SYSTEM_ACTOR, Actor
from src.core.enums import Role
from src.errors.exceptions import AppError
from src.models import utcnow
from src.repositories.sessions.gateway_node_repository import (
    GatewayNodeRepository,
    LostSessionDTO,
)
from src.repositories.sessions.gateway_session_repository import GatewaySessionRepository
from src.services.access.checkout_service import CheckoutService
from src.services.audit.audit_service import AuditService

logger = structlog.get_logger(__name__)

NODE_LOST_REASON = "Gateway node lost"

# Recording fields for a session cut off by a node loss (set by the recordings module).
Salvage = Callable[[LostSessionDTO], Awaitable[dict[str, Any]]]


class HostKeyConflict(Exception):
    """This node's SSH host key is not the one the other gateway nodes present."""


class GatewayNodeService:
    def __init__(
        self,
        nodes: GatewayNodeRepository,
        sessions: GatewaySessionRepository,
        checkouts: CheckoutService,
        audit: AuditService,
    ) -> None:
        self._nodes = nodes
        self._sessions = sessions
        self._checkouts = checkouts
        self._audit = audit

    async def register(
        self, node: str, fingerprint: str, *, expected: str, lost_after: int
    ) -> None:
        """Refuse to start with a host key other than the cluster's; then record the node."""
        if expected and fingerprint != expected:
            raise HostKeyConflict(
                f"gateway host key {fingerprint} is not WARDX_GATEWAY_HOST_KEY_FINGERPRINT "
                f"{expected}: every gateway node must use the same host key file"
            )
        now = utcnow()
        others = [
            n
            for n in await self._nodes.nodes(now - timedelta(seconds=lost_after))
            if n.fresh and n.node != node and n.host_key_fingerprint != fingerprint
        ]
        if others:
            names = ", ".join(f"{n.node} ({n.host_key_fingerprint})" for n in others)
            raise HostKeyConflict(
                f"gateway host key {fingerprint} differs from live node(s) {names}: every "
                "gateway node must use the same host key file (HA_DR.md §5)"
            )
        await self._nodes.register(node, fingerprint, now)
        await self._audit.record(
            SYSTEM_ACTOR,
            "gateway.node_started",
            object_type="cluster",
            details={"node": node, "host_key_fingerprint": fingerprint},
        )
        await self._nodes.commit()

    async def heartbeat(self, node: str) -> None:
        await self._nodes.heartbeat(node, utcnow())
        await self._nodes.commit()

    async def stopped(self, node: str) -> None:
        await self._nodes.stopped(node, utcnow())
        await self._nodes.commit()

    async def sweep_lost(self, lost_after: int, salvage: Salvage | None = None) -> int:
        """End the sessions of nodes silent for ``lost_after`` seconds. One unit of work
        per session; a session another sweeper already ended is skipped."""
        ended = 0
        for lost in await self._nodes.lost_sessions(utcnow() - timedelta(seconds=lost_after)):
            recording = await salvage(lost) if salvage else {}
            values = {
                "status": "terminated",
                "ended_at": utcnow(),
                "close_reason": NODE_LOST_REASON,
                **recording,
            }
            if not await self._sessions.end_if_active(lost.id, values):
                await self._sessions.rollback()
                continue
            await self._audit.record(
                SYSTEM_ACTOR,
                "session.end",
                object_type="session",
                object_id=lost.id,
                outcome="failure",
                details={
                    "status": "terminated",
                    "reason": NODE_LOST_REASON,
                    "gateway": lost.node,
                    "recording_incomplete": bool(recording.get("recording_incomplete")),
                    "recording_sha256": None,
                },
            )
            await self._sessions.commit()
            ended += 1
            logger.warning("gateway_session_node_lost", session_id=str(lost.id), node=lost.node)
            if lost.owns_checkout and lost.checkout_id is not None:
                await self._close_checkout(lost)
        return ended

    async def _close_checkout(self, lost: LostSessionDTO) -> None:
        holder = Actor(id=lost.user_id, username=lost.username, role=Role(lost.role))
        try:
            await self._checkouts.checkin(holder, lost.checkout_id)
        except AppError:
            # Already expired, revoked or returned: nothing to close.
            await self._sessions.rollback()
