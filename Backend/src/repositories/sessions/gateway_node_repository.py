"""Gateway node heartbeats (ha.gateway_nodes) and the sessions of lost nodes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text

from src.contracts.dto.health.cluster_dto import GatewayNodeDTO
from src.repositories.base import BaseRepository


@dataclass(frozen=True)
class LostSessionDTO:
    id: uuid.UUID
    node: str
    user_id: uuid.UUID
    username: str
    role: str
    checkout_id: uuid.UUID | None
    owns_checkout: bool


class GatewayNodeRepository(BaseRepository):
    async def register(self, node: str, fingerprint: str, now: datetime) -> None:
        await self._session.execute(
            text(
                "INSERT INTO ha.gateway_nodes (node, started_at, last_seen, host_key_fingerprint) "
                "VALUES (:n, :now, :now, :fp) ON CONFLICT (node) DO UPDATE SET "
                "started_at = EXCLUDED.started_at, last_seen = EXCLUDED.last_seen, "
                "host_key_fingerprint = EXCLUDED.host_key_fingerprint, stopped_at = NULL"
            ),
            {"n": node, "fp": fingerprint, "now": now},
        )

    async def heartbeat(self, node: str, now: datetime) -> None:
        await self._session.execute(
            text("UPDATE ha.gateway_nodes SET last_seen = :now WHERE node = :n"),
            {"n": node, "now": now},
        )

    async def stopped(self, node: str, now: datetime) -> None:
        await self._session.execute(
            text("UPDATE ha.gateway_nodes SET stopped_at = :now WHERE node = :n"),
            {"n": node, "now": now},
        )

    async def nodes(self, fresh_after: datetime) -> list[GatewayNodeDTO]:
        rows = await self._session.execute(
            text(
                "SELECT node, started_at, last_seen, host_key_fingerprint, stopped_at, "
                "(stopped_at IS NULL AND last_seen >= :f) AS fresh "
                "FROM ha.gateway_nodes ORDER BY node"
            ),
            {"f": fresh_after},
        )
        return [GatewayNodeDTO(*r) for r in rows.all()]

    async def active_on_node(self, node: str, limit: int = 500) -> list[LostSessionDTO]:
        """This node's sessions still marked active (left by its previous run)."""
        rows = await self._session.execute(
            text(
                "SELECT s.id, s.gateway_node, s.user_id, u.username, u.role, s.checkout_id, "
                "s.owns_checkout FROM access.sessions s JOIN iam.users u ON u.id = s.user_id "
                "WHERE s.status = 'active' AND s.gateway_node = :n "
                "ORDER BY s.started_at LIMIT :lim"
            ),
            {"n": node, "lim": limit},
        )
        return [LostSessionDTO(*r) for r in rows.all()]

    async def lost_sessions(self, cutoff: datetime, limit: int = 200) -> list[LostSessionDTO]:
        """Active sessions whose node stopped heartbeating before ``cutoff`` (or never
        registered, for a session older than ``cutoff``)."""
        rows = await self._session.execute(
            text(
                "SELECT s.id, s.gateway_node, s.user_id, u.username, u.role, s.checkout_id, "
                "s.owns_checkout FROM access.sessions s "
                "JOIN iam.users u ON u.id = s.user_id "
                "LEFT JOIN ha.gateway_nodes g ON g.node = s.gateway_node "
                "WHERE s.status = 'active' AND ("
                "  (g.node IS NOT NULL AND g.last_seen < :c) "
                "  OR (g.node IS NULL AND s.started_at < :c)) "
                "ORDER BY s.started_at LIMIT :lim"
            ),
            {"c": cutoff, "lim": limit},
        )
        return [LostSessionDTO(*r) for r in rows.all()]
