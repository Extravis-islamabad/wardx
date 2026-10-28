"""SSH host keys pinned per target (ROTATION.md §14, fix 4).

- Probe: read the key a target presents, without authenticating (nothing is sent),
  and show its SHA256 fingerprint next to the pinned one.
- Accept: an administrator who compared the fingerprint with the device accepts it.
  The key is read again and pinned only if it still has the fingerprint the
  administrator saw, so a key swapped between probe and accept is refused.
  Accepting replaces an existing pin (a re-learn) and clears a recorded mismatch.
- A device presenting another key (seen by the gateway, a rotation or a verify)
  records a mismatch on the target, raises one high alert per new key, and blocks
  rotation and verify until a key is accepted again. It is never accepted
  automatically.
- The gateway still pins a target's first-seen key on its first session (trust on
  first use); a different key after that is always a mismatch.

Probing, accepting and resetting need inventory.manage and manage_accounts on every
safe holding an account on the target. Every change is audited once at target
level and once per affected safe.
"""

from __future__ import annotations

import asyncio
import uuid

import asyncssh

from src.contracts.dto.inventory.target_dto import TargetDTO
from src.contracts.dto.sessions.host_key_dto import HostKeyProbeDTO
from src.core.config import get_settings
from src.core.context import Actor
from src.errors.exceptions import ConflictError
from src.models import utcnow
from src.services.sessions.target_identity import TargetIdentityService
from src.transport.ssh import openssh_public

MISMATCH_ALERT = "target.host_key_changed"


class HostKeyService(TargetIdentityService):
    @staticmethod
    async def _read_key(target: TargetDTO) -> asyncssh.SSHKey:
        if target.protocol != "ssh":
            raise ConflictError("Only SSH targets have host keys")
        timeout = get_settings().target_connect_timeout_seconds
        try:
            key = await asyncio.wait_for(
                asyncssh.get_server_host_key(target.address, target.port), timeout
            )
        except (OSError, asyncssh.Error, TimeoutError) as exc:
            raise ConflictError(f"Could not read the host key of {target.name}: {exc}") from exc
        if key is None:
            raise ConflictError(f"{target.name} did not present a host key")
        return key

    # ── administrator actions ──

    async def probe(self, actor: Actor, target_id: uuid.UUID) -> HostKeyProbeDTO:
        """The key the target presents now, for comparison. Changes nothing."""
        target = await self._target(target_id)
        await self._require_manage(actor, target_id)
        key = await self._read_key(target)
        fingerprint = key.get_fingerprint("sha256")
        return HostKeyProbeDTO(
            target_id=target.id,
            presented_fingerprint=fingerprint,
            key_type=key.get_algorithm(),
            pinned_fingerprint=target.ssh_host_key_fingerprint,
            matches_pin=fingerprint == target.ssh_host_key_fingerprint,
            mismatch_at=target.host_key_mismatch_at,
            mismatch_fingerprint=target.host_key_mismatch_fingerprint,
        )

    async def accept(self, actor: Actor, target_id: uuid.UUID, fingerprint: str) -> TargetDTO:
        """Pin the presented key, only if it still has the fingerprint the administrator
        compared with the device."""
        target = await self._target(target_id)
        safe_ids = await self._require_manage(actor, target_id)
        key = await self._read_key(target)
        presented = key.get_fingerprint("sha256")
        if presented != fingerprint.strip():
            await self._audit_per_safe(
                actor,
                "target.host_key_accept",
                target_id,
                safe_ids,
                {"expected": fingerprint, "presented": presented},
                outcome="failure",
            )
            await self._targets.commit()
            raise ConflictError(
                "The device now presents a different key than the one you compared. "
                "Read it again and compare before accepting.",
                {"presented_fingerprint": presented},
            )
        previous = target.ssh_host_key_fingerprint
        if previous == presented and target.host_key_mismatch_at is None:
            raise ConflictError("This key is already pinned")
        await self._targets.accept_host_key(
            target_id, key=openssh_public(key), fingerprint=presented, learned_at=utcnow()
        )
        action = "target.host_key_learned" if previous is None else "target.host_key_changed"
        await self._audit_per_safe(
            actor,
            action,
            target_id,
            safe_ids,
            {
                "fingerprint": presented,
                "previous_fingerprint": previous,
                "cleared_mismatch": target.host_key_mismatch_fingerprint,
                "via": "accept",
            },
        )
        await self._targets.commit()
        return await self._target(target_id)

    async def reset(self, actor: Actor, target_id: uuid.UUID) -> TargetDTO:
        """Clear the pin (the next gateway session pins the key it sees, or an
        administrator accepts one). Rotation stays refused until a key is pinned."""
        target = await self._target(target_id)
        safe_ids = await self._require_manage(actor, target_id)
        updated = await self._targets.update(
            target_id,
            {
                "ssh_host_key": None,
                "ssh_host_key_fingerprint": None,
                "ssh_host_key_learned_at": None,
            },
        )
        await self._audit_per_safe(
            actor,
            "target.host_key_reset",
            target_id,
            safe_ids,
            {"previous_fingerprint": target.ssh_host_key_fingerprint},
        )
        await self._targets.commit()
        return updated

    # ── seen by the gateway, a rotation or a verify ──

    async def pin(
        self,
        actor: Actor,
        target_id: uuid.UUID,
        *,
        key: str,
        fingerprint: str,
        session_id: uuid.UUID,
    ) -> bool:
        """Trust on first use (gateway): pin a target's first-seen key. False if a key
        is already pinned (then the session compares against that pin)."""
        pinned = await self._targets.pin_host_key(
            target_id, key=key, fingerprint=fingerprint, learned_at=utcnow()
        )
        if not pinned:
            await self._targets.rollback()
            return False
        await self._audit_per_safe(
            actor,
            "target.host_key_learned",
            target_id,
            await self._safe_ids(target_id),
            {"fingerprint": fingerprint, "session_id": str(session_id), "via": "first_use"},
        )
        await self._targets.commit()
        return True

    async def record_mismatch(
        self,
        actor: Actor,
        target_id: uuid.UUID,
        *,
        presented: str | None,
        session_id: uuid.UUID | None = None,
        source: str = "gateway",
    ) -> bool:
        """A device presented a key other than the pinned one. Records it on the target
        (blocking rotation and verify), audits it, and raises one high alert per new
        presented key. True when this was a new mismatch."""
        target = await self._targets.get(target_id)
        if target is None:
            return False
        new = await self._targets.record_host_key_mismatch(
            target_id, presented=presented, seen_at=utcnow()
        )
        details = {
            "pinned_fingerprint": target.ssh_host_key_fingerprint,
            "presented_fingerprint": presented,
            "source": source,
            "session_id": str(session_id) if session_id else None,
        }
        await self._audit_per_safe(
            actor,
            "target.host_key_mismatch",
            target_id,
            await self._safe_ids(target_id),
            details,
            outcome="failure",
        )
        if new:
            await self._alerts.raise_alert(
                actor,
                kind=MISMATCH_ALERT,
                message=(
                    f"{target.name} presented host key {presented or '(unreadable)'} instead "
                    f"of the pinned {target.ssh_host_key_fingerprint}. Rotation and verify "
                    "are blocked until an administrator compares and accepts a key."
                ),
                object_type="target",
                object_id=target_id,
                details=details,
            )
        await self._targets.commit()
        return new
