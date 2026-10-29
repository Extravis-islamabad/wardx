"""Security alerts: raised in the caller's transaction, listed, acknowledged.

Alerts are never deleted (a database trigger enforces it); acknowledging one is
audited and is the only change an alert ever gets.
"""

from __future__ import annotations

import uuid
from typing import Any

from src.contracts.dto.security.alert_dto import AlertDTO, AlertFilterDTO
from src.core.context import Actor
from src.errors.exceptions import ConflictError, NotFoundError
from src.models import utcnow
from src.repositories.security.alert_repository import AlertRepository
from src.services.audit.audit_service import AuditService

HIGH = "high"


class AlertService:
    def __init__(self, alerts: AlertRepository, audit: AuditService) -> None:
        self._alerts = alerts
        self._audit = audit

    async def raise_alert(
        self,
        actor: Actor,
        *,
        kind: str,
        message: str,
        severity: str = HIGH,
        object_type: str | None = None,
        object_id: uuid.UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> AlertDTO:
        """Add an alert in the caller's transaction (the caller commits)."""
        return await self._alerts.add(
            {
                "severity": severity,
                "kind": kind,
                "message": message,
                "actor_id": actor.id,
                "actor_name": actor.username,
                "object_type": object_type,
                "object_id": object_id,
                "details": details or {},
            }
        )

    async def clear(self, kind: str, object_id: uuid.UUID) -> list[uuid.UUID]:
        """A condition recovered: the system acknowledges its open alerts of ``kind``
        (in the caller's transaction; the caller audits the recovery and commits)."""
        ids = await self._alerts.open_ids_for(kind, object_id)
        for alert_id in ids:
            await self._alerts.acknowledge(alert_id, None, utcnow())
        return ids

    async def list(
        self, filters: AlertFilterDTO, *, page: int, page_size: int
    ) -> tuple[list[AlertDTO], int]:
        return await self._alerts.list(filters, page=page, page_size=page_size)

    async def acknowledge(self, actor: Actor, alert_id: uuid.UUID) -> AlertDTO:
        alert = await self._alerts.get(alert_id, lock=True)
        if alert is None:
            raise NotFoundError("Alert not found")
        if alert.acknowledged_at is not None:
            raise ConflictError("Alert is already acknowledged")
        await self._alerts.acknowledge(alert_id, actor.id, utcnow())
        await self._audit.record(
            actor,
            "alert.acknowledge",
            object_type="alert",
            object_id=alert_id,
            details={"kind": alert.kind, "severity": alert.severity},
        )
        await self._alerts.commit()
        return await self._alerts.get(alert_id)
