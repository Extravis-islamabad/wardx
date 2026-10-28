"""SSH host keys the gateway pins per target (trust on first use).

The first session to a target pins the key it presents; a different key later
refuses the session and is audited. An administrator clears a pin after a
legitimate key change so the next session pins the new one.
"""

from __future__ import annotations

import uuid

from src.contracts.dto.inventory.target_dto import TargetDTO
from src.core.context import Actor
from src.errors.exceptions import NotFoundError
from src.repositories.inventory.target_repository import TargetRepository
from src.services.audit.audit_service import AuditService


class HostKeyService:
    def __init__(self, targets: TargetRepository, audit: AuditService) -> None:
        self._targets = targets
        self._audit = audit

    async def reset(self, actor: Actor, target_id: uuid.UUID) -> TargetDTO:
        target = await self._targets.get(target_id, lock=True)
        if target is None:
            raise NotFoundError("Target not found")
        updated = await self._targets.update(
            target_id,
            {
                "ssh_host_key": None,
                "ssh_host_key_fingerprint": None,
                "ssh_host_key_learned_at": None,
            },
        )
        await self._audit.record(
            actor,
            "target.host_key_reset",
            object_type="target",
            object_id=target.id,
            details={"previous_fingerprint": target.ssh_host_key_fingerprint},
        )
        await self._targets.commit()
        return updated
