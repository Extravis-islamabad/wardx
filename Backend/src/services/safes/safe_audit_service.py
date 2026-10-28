"""Safe-scoped audit: events about a safe, its accounts, and their requests and check-outs.

Needs 'view_audit' on the safe; holders of the global audit.view can read any safe's.
A member without view_audit gets 403; someone who cannot list the safe gets 404.
Limitation: events of accounts deleted from (or moved out of) the safe are not included;
the global audit trail still has them.
"""

from __future__ import annotations

import uuid
from dataclasses import replace

from src.contracts.dto.audit.audit_event_dto import AuditEventDTO, AuditFilterDTO
from src.core.context import Actor
from src.core.enums import SafePermission
from src.core.permissions import AUDIT_VIEW
from src.errors.exceptions import NotFoundError
from src.repositories.safes.safe_repository import SafeRepository
from src.services.audit.audit_service import AuditService
from src.services.safes.safe_access_service import SafeAccessService


class SafeAuditService:
    def __init__(
        self, safes: SafeRepository, access: SafeAccessService, audit: AuditService
    ) -> None:
        self._safes = safes
        self._access = access
        self._audit = audit

    async def list(
        self,
        actor: Actor,
        safe_id: uuid.UUID,
        filters: AuditFilterDTO,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[AuditEventDTO], int]:
        if actor.can(AUDIT_VIEW):
            if await self._safes.get(safe_id) is None:
                raise NotFoundError("Safe not found")
        else:
            await self._access.require(actor, safe_id, SafePermission.VIEW_AUDIT, what="Safe")
        return await self._audit.list_events(
            replace(filters, safe_id=safe_id), page=page, page_size=page_size
        )
