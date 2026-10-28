"""A safe's rotation policy: read (safes.manage or 'list') and save (safes.manage, audited)."""

from __future__ import annotations

import uuid
from typing import Any

from src.contracts.dto.rotation.rotation_dto import SafeRotationPolicyDTO
from src.core.context import Actor
from src.core.permissions import SAFES_MANAGE
from src.errors.exceptions import AppError, NotFoundError
from src.repositories.rotation.rotation_account_repository import RotationAccountRepository
from src.services.audit.audit_service import AuditService
from src.services.safes.safe_access_service import SafeAccessService


class InvalidRotationPolicy(AppError):
    status_code = 422
    code = "invalid_policy"


def check_window(window: dict[str, Any] | None) -> dict[str, Any] | None:
    """A maintenance window: {days: [0..6] (Monday = 0), start_hour, end_hour} in UTC."""
    if not window:
        return None
    days = sorted({int(d) for d in window.get("days") or []})
    if not days or any(d < 0 or d > 6 for d in days):
        raise InvalidRotationPolicy("Maintenance window days are 0 (Monday) to 6 (Sunday)")
    start, end = int(window.get("start_hour", 0)), int(window.get("end_hour", 24))
    if not 0 <= start < end <= 24:
        raise InvalidRotationPolicy("Maintenance window hours: 0 ≤ start < end ≤ 24 (UTC)")
    return {"days": days, "start_hour": start, "end_hour": end}


class SafeRotationPolicyService:
    def __init__(
        self,
        accounts: RotationAccountRepository,
        access: SafeAccessService,
        audit: AuditService,
    ) -> None:
        self._accounts = accounts
        self._access = access
        self._audit = audit

    async def get(self, actor: Actor, safe_id: uuid.UUID) -> SafeRotationPolicyDTO:
        if not actor.can(SAFES_MANAGE):
            await self._access.require(actor, safe_id, what="Safe")
        found = await self._accounts.safe_policy(safe_id)
        if found is None:
            raise NotFoundError("Safe not found")
        return found

    async def save(
        self, actor: Actor, safe_id: uuid.UUID, values: dict[str, Any]
    ) -> SafeRotationPolicyDTO:
        before = await self._accounts.safe_policy(safe_id)
        if before is None:
            raise NotFoundError("Safe not found")
        values = {**values, "maintenance_window": check_window(values.get("maintenance_window"))}
        await self._accounts.save_safe_policy(safe_id, values)
        after = await self._accounts.safe_policy(safe_id)
        await self._audit.record(
            actor,
            "safe.rotation_policy_update",
            object_type="safe",
            object_id=safe_id,
            safe_id=safe_id,
            details={"before": before.audit_view(), "after": after.audit_view()},
        )
        await self._accounts.commit()
        return after
