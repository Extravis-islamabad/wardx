"""Cluster state: leadership row, replication views, conditions (ha.*, pg_stat_replication)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import text

from src.contracts.dto.health.cluster_dto import (
    ConditionDTO,
    GatewayNodeDTO,
    LeaderDTO,
    ReplicaDTO,
)
from src.repositories.base import BaseRepository


class ClusterRepository(BaseRepository):
    # ── Scheduler leadership (display and audit; the advisory lock decides) ──

    async def leader(self) -> LeaderDTO | None:
        row = (
            await self._session.execute(
                text("SELECT node, term, elected_at, last_seen FROM ha.scheduler_leader")
            )
        ).first()
        return LeaderDTO(*row) if row else None

    async def claim_leader_row(self, node: str, now: datetime) -> tuple[int, str | None]:
        """Record ``node`` as leader; returns (new term, previous leader node)."""
        prev = (
            await self._session.execute(
                text("SELECT node, term FROM ha.scheduler_leader WHERE id = 1 FOR UPDATE")
            )
        ).first()
        term = (prev.term if prev else 0) + 1
        await self._session.execute(
            text(
                "INSERT INTO ha.scheduler_leader (id, node, term, elected_at, last_seen) "
                "VALUES (1, :node, :term, :now, :now) ON CONFLICT (id) DO UPDATE SET "
                "node = EXCLUDED.node, term = EXCLUDED.term, elected_at = EXCLUDED.elected_at, "
                "last_seen = EXCLUDED.last_seen"
            ),
            {"node": node, "term": term, "now": now},
        )
        return term, (prev.node if prev else None)

    # ── Replication (read on the primary) ──

    async def in_recovery(self) -> bool:
        return bool((await self._session.execute(text("SELECT pg_is_in_recovery()"))).scalar())

    async def replicas(self) -> list[ReplicaDTO]:
        rows = await self._session.execute(
            text(
                "SELECT application_name, state, sync_state, "
                "EXTRACT(EPOCH FROM replay_lag)::float8 AS lag, "
                "CASE WHEN pg_is_in_recovery() THEN NULL "
                "ELSE pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)::bigint END AS lag_bytes "
                "FROM pg_stat_replication ORDER BY application_name"
            )
        )
        return [ReplicaDTO(*r) for r in rows.all()]

    async def gateway_nodes(self, fresh_after: datetime) -> list[GatewayNodeDTO]:
        rows = await self._session.execute(
            text(
                "SELECT node, started_at, last_seen, host_key_fingerprint, stopped_at, "
                "(stopped_at IS NULL AND last_seen >= :f) AS fresh "
                "FROM ha.gateway_nodes ORDER BY node"
            ),
            {"f": fresh_after},
        )
        return [GatewayNodeDTO(*r) for r in rows.all()]

    # ── Conditions ──

    async def condition(self, kind: str) -> ConditionDTO | None:
        row = (
            await self._session.execute(
                text(
                    "SELECT kind, active, since, checked_at, details, alert_id "
                    "FROM ha.conditions WHERE kind = :k FOR UPDATE"
                ),
                {"k": kind},
            )
        ).first()
        return ConditionDTO(*row) if row else None

    async def conditions(self) -> list[ConditionDTO]:
        rows = await self._session.execute(
            text(
                "SELECT kind, active, since, checked_at, details, alert_id "
                "FROM ha.conditions ORDER BY kind"
            )
        )
        return [ConditionDTO(*r) for r in rows.all()]

    async def put_condition(
        self,
        kind: str,
        *,
        active: bool,
        since: datetime,
        now: datetime,
        details: dict[str, Any],
        alert_id: uuid.UUID | None,
    ) -> None:
        await self._session.execute(
            text(
                "INSERT INTO ha.conditions (kind, active, since, checked_at, details, alert_id) "
                "VALUES (:k, :a, :s, :n, CAST(:d AS JSONB), :al) ON CONFLICT (kind) DO UPDATE "
                "SET active = EXCLUDED.active, since = EXCLUDED.since, "
                "checked_at = EXCLUDED.checked_at, details = EXCLUDED.details, "
                "alert_id = EXCLUDED.alert_id"
            ),
            {
                "k": kind,
                "a": active,
                "s": since,
                "n": now,
                "d": json.dumps(details),
                "al": alert_id,
            },
        )
