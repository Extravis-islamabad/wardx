"""Transitional shim over AuditService for modules not yet on the layered services."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.dto.audit.audit_event_dto import AuditEventDTO
from src.core.context import Actor
from src.repositories.audit.audit_event_repository import AuditEventRepository
from src.services.audit.audit_service import AuditService


async def record(
    session: AsyncSession,
    actor: Actor,
    action: str,
    *,
    object_type: str | None = None,
    object_id: uuid.UUID | None = None,
    outcome: str = "success",
    details: dict[str, Any] | None = None,
) -> AuditEventDTO:
    return await AuditService(AuditEventRepository(session)).record(
        actor,
        action,
        object_type=object_type,
        object_id=object_id,
        outcome=outcome,
        details=details,
    )
