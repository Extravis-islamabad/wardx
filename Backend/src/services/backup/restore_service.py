"""Restore verification and drills (HA_DR.md §7).

Run against a restored database (never a live one), after the node started with the
escrowed keys (the KEK canary check already passed at startup):

- the audit chain must verify up to the restore point;
- a sample of secrets must decrypt;
- accounts rotated after the restore point are out of sync by definition and listed for
  reconcile (from ``last_rotated_at``).

A drill's result is then recorded on the production database and shown on the dashboard.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from src.core.context import SYSTEM_ACTOR
from src.errors.exceptions import AppError
from src.repositories.health.restore_repository import RestoreRepository
from src.services.audit.audit_service import AuditService
from src.services.inventory.account_service import ACCOUNT_SECRET
from src.services.vault.vault_service import VaultService


class RestoreService:
    def __init__(self, repo: RestoreRepository, audit: AuditService, vault: VaultService) -> None:
        self._repo = repo
        self._audit = audit
        self._vault = vault

    async def verify(self, *, sample: int, restore_point: datetime | None) -> dict[str, Any]:
        chain = await self._audit.verify_chain()
        decrypted = failed = 0
        for account_id, version in await self._repo.sample_accounts(sample):
            try:
                await self._vault.read(
                    owner_type=ACCOUNT_SECRET, owner_id=account_id, version=version
                )
                decrypted += 1
            except AppError:
                failed += 1
        rotated = await self._repo.rotated_after(restore_point) if restore_point else []
        await self._repo.rollback()
        ok = chain.ok and failed == 0
        return {
            "ok": ok,
            "canary": "ok",  # startup refuses to run otherwise
            "audit_chain": {
                "ok": chain.ok,
                "checked": chain.checked,
                "broken_at_seq": chain.broken_at_seq,
                "reason": chain.reason,
            },
            "secrets_sampled": decrypted + failed,
            "secrets_decrypted": decrypted,
            "secrets_failed": failed,
            "restore_point": restore_point.isoformat() if restore_point else None,
            "rotated_after_restore_point": rotated,
        }

    async def record_drill(self, result: dict[str, Any]) -> uuid.UUID:
        point = result.get("restore_point")
        drill_id = await self._repo.record_drill(
            ok=bool(result.get("ok")),
            restore_point=datetime.fromisoformat(point) if point else None,
            details=result,
        )
        await self._audit.record(
            SYSTEM_ACTOR,
            "backup.restore_drill",
            object_type="cluster",
            outcome="success" if result.get("ok") else "failure",
            details={
                "drill_id": str(drill_id),
                "ok": bool(result.get("ok")),
                "secrets_sampled": result.get("secrets_sampled"),
                "audit_events_checked": (result.get("audit_chain") or {}).get("checked"),
                "rotated_after_restore_point": len(result.get("rotated_after_restore_point") or []),
            },
        )
        await self._repo.commit()
        return drill_id
