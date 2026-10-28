"""SSH host keys the gateway pins per target (trust on first use).

The first session to a target pins the key it presents; a different key later
refuses the session and is audited. An administrator clears a pin after a
legitimate key change so the next session pins the new one.
"""

from __future__ import annotations

import asyncio
import uuid

import asyncssh

from src.contracts.dto.inventory.target_dto import TargetDTO
from src.core.config import get_settings
from src.core.context import Actor
from src.errors.exceptions import ConflictError, NotFoundError
from src.models import utcnow
from src.repositories.inventory.target_repository import TargetRepository
from src.services.audit.audit_service import AuditService
from src.transport.ssh import openssh_public


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

    async def pin(
        self,
        actor: Actor,
        target_id: uuid.UUID,
        *,
        key: str,
        fingerprint: str,
        session_id: uuid.UUID,
    ) -> bool:
        """Pin a target's first-seen host key. False if another key got pinned first."""
        pinned = await self._targets.pin_host_key(
            target_id, key=key, fingerprint=fingerprint, learned_at=utcnow()
        )
        if not pinned:
            await self._targets.rollback()
            return False
        await self._audit.record(
            actor,
            "target.host_key_learned",
            object_type="target",
            object_id=target_id,
            details={"fingerprint": fingerprint, "session_id": str(session_id)},
        )
        await self._targets.commit()
        return True

    async def record_mismatch(
        self, actor: Actor, target_id: uuid.UUID, *, presented: str | None, session_id: uuid.UUID
    ) -> None:
        """Audit a device presenting a host key other than the pinned one."""
        await self._audit.record(
            actor,
            "target.host_key_mismatch",
            object_type="target",
            object_id=target_id,
            outcome="failure",
            details={"presented_fingerprint": presented, "session_id": str(session_id)},
        )
        await self._targets.commit()

    async def learn(self, actor: Actor, target_id: uuid.UUID) -> TargetDTO:
        """Pin the key the target presents now (trust on first use, with no login).

        Rotation never pins a key itself; this is how an administrator pins one for a
        target nobody has opened a gateway session to yet. An existing pin is never
        replaced here: reset it first.
        """
        target = await self._targets.get(target_id)
        if target is None:
            raise NotFoundError("Target not found")
        if target.protocol != "ssh":
            raise ConflictError("Only SSH targets have host keys")
        if target.ssh_host_key:
            raise ConflictError("A host key is already pinned; reset it first to re-learn")
        timeout = get_settings().target_connect_timeout_seconds
        try:
            key = await asyncio.wait_for(
                asyncssh.get_server_host_key(target.address, target.port), timeout
            )
        except (OSError, asyncssh.Error, TimeoutError) as exc:
            raise ConflictError(f"Could not read the host key of {target.name}: {exc}") from exc
        if key is None:
            raise ConflictError(f"{target.name} did not present a host key")
        fingerprint = key.get_fingerprint("sha256")
        pinned = await self._targets.pin_host_key(
            target_id, key=openssh_public(key), fingerprint=fingerprint, learned_at=utcnow()
        )
        if not pinned:
            await self._targets.rollback()
            raise ConflictError("Another key was pinned meanwhile")
        await self._audit.record(
            actor,
            "target.host_key_learned",
            object_type="target",
            object_id=target_id,
            details={"fingerprint": fingerprint, "via": "learn"},
        )
        await self._targets.commit()
        return await self._targets.get(target_id)
