"""What the SSH host-key and TLS certificate pins of a target share (ROTATION.md §14, §15).

Both are probed (shown, nothing pinned), accepted only if the device still presents
exactly what the administrator compared, and recorded as a mismatch (blocking rotation
and verify) when a device presents something else. Changing either needs
inventory.manage (checked by the route) plus manage_accounts on every safe that holds
an account on the target, and is audited once at target level and once per safe.
"""

from __future__ import annotations

import uuid
from typing import Any

from src.contracts.dto.inventory.target_dto import TargetDTO
from src.core.context import Actor
from src.core.enums import SafePermission
from src.errors.exceptions import ForbiddenError, NotFoundError
from src.repositories.inventory.account_repository import AccountRepository
from src.repositories.inventory.target_repository import TargetRepository
from src.services.audit.audit_service import AuditService
from src.services.safes.safe_access_service import SafeAccessService
from src.services.security.alert_service import AlertService


class TargetIdentityService:
    def __init__(
        self,
        targets: TargetRepository,
        accounts: AccountRepository,
        access: SafeAccessService,
        alerts: AlertService,
        audit: AuditService,
    ) -> None:
        self._targets = targets
        self._accounts = accounts
        self._access = access
        self._alerts = alerts
        self._audit = audit

    async def _target(self, target_id: uuid.UUID) -> TargetDTO:
        target = await self._targets.get(target_id)
        if target is None:
            raise NotFoundError("Target not found")
        return target

    async def _safe_ids(self, target_id: uuid.UUID) -> list[uuid.UUID]:
        accounts = await self._accounts.list_for_target(target_id)
        return sorted({a.safe_id for a in accounts}, key=str)

    async def _require_manage(self, actor: Actor, target_id: uuid.UUID) -> list[uuid.UUID]:
        """manage_accounts on every safe holding an account on the target (the route
        already requires inventory.manage). A target with no accounts needs nothing more."""
        safe_ids = await self._safe_ids(target_id)
        for safe_id in safe_ids:
            perms = await self._access.permissions(actor, safe_id)
            if SafePermission.MANAGE_ACCOUNTS not in perms:
                raise ForbiddenError(
                    "The identity pins of this target can only be changed with "
                    "manage_accounts on every safe that holds one of its accounts"
                )
        return safe_ids

    async def _audit_per_safe(
        self,
        actor: Actor,
        action: str,
        target_id: uuid.UUID,
        safe_ids: list[uuid.UUID],
        details: dict[str, Any],
        outcome: str = "success",
    ) -> None:
        """One target-level event, then one per affected safe."""
        await self._audit.record(
            actor,
            action,
            object_type="target",
            object_id=target_id,
            outcome=outcome,
            details=details,
        )
        for safe_id in safe_ids:
            await self._audit.record(
                actor,
                action,
                object_type="target",
                object_id=target_id,
                safe_id=safe_id,
                outcome=outcome,
                details=details,
            )
