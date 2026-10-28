"""A safe's credential-provider settings (docs/phase1/CREDENTIAL_PROVIDER.md §3, §4).

- ``allow_app_fetch``: apps may fetch from the safe although it requires approval for
  people. Off by default.
- ``app_cache_seconds``: the ``max_cache_seconds`` served to apps (0 to 3600, default 300).
Reading needs ``list`` on the safe (or safes.manage); changing needs ``manage_members``
on it (or safes.manage), like any change to who gets in. Every change is audited.
"""

from __future__ import annotations

import uuid
from typing import Any

from src.contracts.dto.safes.safe_dto import SafeDTO
from src.core.context import Actor
from src.core.enums import SafePermission
from src.core.permissions import SAFES_MANAGE
from src.errors.exceptions import NotFoundError
from src.repositories.safes.safe_repository import SafeRepository
from src.services.audit.audit_service import AuditService
from src.services.safes.safe_access_service import SafeAccessService


class SafeAppFetchService:
    def __init__(
        self, safes: SafeRepository, access: SafeAccessService, audit: AuditService
    ) -> None:
        self._safes = safes
        self._access = access
        self._audit = audit

    async def get(self, actor: Actor, safe_id: uuid.UUID) -> SafeDTO:
        if not actor.can(SAFES_MANAGE):
            await self._access.require(actor, safe_id, what="Safe")
        safe = await self._safes.get(safe_id)
        if safe is None:
            raise NotFoundError("Safe not found")
        return safe

    async def save(self, actor: Actor, safe_id: uuid.UUID, values: dict[str, Any]) -> SafeDTO:
        if not actor.can(SAFES_MANAGE):
            await self._access.require(actor, safe_id, SafePermission.MANAGE_MEMBERS, what="Safe")
        before = await self._safes.get(safe_id, lock=True)
        if before is None:
            raise NotFoundError("Safe not found")
        await self._safes.update(safe_id, values)
        after = await self._safes.get(safe_id)
        await self._audit.record(
            actor,
            "safe.app_fetch_update",
            object_type="safe",
            object_id=safe_id,
            safe_id=safe_id,
            details={"before": before.app_fetch_view(), "after": after.app_fetch_view()},
        )
        await self._safes.commit()
        return after
