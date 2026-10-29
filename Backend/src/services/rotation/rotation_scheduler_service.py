"""The scheduler's rotation housekeeping, one committed unit of work per call.

- release: waiting jobs with no holder left become pending; waits past the safe's
  ``max_release_wait_minutes`` raise one high alert and keep waiting (never forced).
- enqueue: scheduled rotations (within the safe's maintenance window) and verifies,
  only while the global switch is on and only on targets that allow rotation.
- scan: flag accounts whose stored password is empty (high_risk_empty_password).
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

from src.contracts.dto.rotation.rotation_dto import (
    HIGH_RISK_EMPTY_PASSWORD,
    PENDING,
    SCHEDULE,
    VERIFY,
)
from src.core.context import SYSTEM_ACTOR
from src.errors.exceptions import ConflictError
from src.models import utcnow
from src.repositories.rotation.rotation_account_repository import RotationAccountRepository
from src.repositories.rotation.rotation_job_repository import RotationJobRepository
from src.services.audit.audit_service import AuditService
from src.services.inventory.account_service import ACCOUNT_SECRET
from src.services.security.alert_service import AlertService
from src.services.vault.vault_service import VaultService


def in_window(window: dict[str, Any] | None, now: datetime) -> bool:
    """Whether ``now`` (UTC) is inside a maintenance window; no window = any time."""
    if not window:
        return True
    days = window.get("days") or list(range(7))
    start, end = int(window.get("start_hour", 0)), int(window.get("end_hour", 24))
    return now.weekday() in days and start <= now.hour < end


class RotationSchedulerService:
    def __init__(
        self,
        jobs: RotationJobRepository,
        accounts: RotationAccountRepository,
        vault: VaultService,
        audit: AuditService,
        alerts: AlertService,
    ) -> None:
        self._jobs = jobs
        self._accounts = accounts
        self._vault = vault
        self._audit = audit
        self._alerts = alerts

    async def release_waiting(self, now: datetime | None = None) -> dict[str, int]:
        now = now or utcnow()
        released = alerted = 0
        for job in await self._jobs.waiting():
            holders = await self._accounts.holders(job.account_id)
            if not any(holders.values()):
                await self._jobs.update(job.id, {"status": PENDING, "not_before": now})
                await self._accounts.update(job.account_id, {"rotation_status": PENDING})
                released += 1
                continue
            policy = await self._accounts.safe_policy(job.safe_id)
            limit = timedelta(minutes=policy.max_release_wait_minutes if policy else 240)
            since = job.waiting_since or job.created_at
            if job.release_alerted_at is None and now - since > limit:
                await self._jobs.update(job.id, {"release_alerted_at": now})
                await self._alerts.raise_alert(
                    SYSTEM_ACTOR,
                    kind="rotation.release_wait_exceeded",
                    message=(
                        f"Rotation of {job.account_username}@{job.target_name} has waited "
                        f"over {int(limit.total_seconds() // 60)} minutes for holders to "
                        "release it; it keeps waiting and never rotates under a holder"
                    ),
                    object_type="account",
                    object_id=job.account_id,
                    details={"job_id": str(job.id), "safe_id": str(job.safe_id), **holders},
                )
                await self._audit.record(
                    SYSTEM_ACTOR,
                    "rotation.release_wait_exceeded",
                    object_type="rotation_job",
                    object_id=job.id,
                    safe_id=job.safe_id,
                    details={"account_id": str(job.account_id), **holders},
                )
                alerted += 1
        await self._jobs.commit()
        return {"released": released, "alerted": alerted}

    async def _enqueue(self, account_id: uuid.UUID, safe_id: uuid.UUID, reason: str, at) -> bool:
        try:
            job_id = await self._jobs.create(
                {
                    "account_id": account_id,
                    "target_id": await self._accounts.target_id_of(account_id),
                    "reason": reason,
                    "status": PENDING,
                    "not_before": at,
                }
            )
        except ConflictError:
            return False
        await self._audit.record(
            SYSTEM_ACTOR,
            "rotation.queued",
            object_type="rotation_job",
            object_id=job_id,
            safe_id=safe_id,
            details={"account_id": str(account_id), "reason": reason},
        )
        return True

    async def enqueue_due(
        self,
        *,
        enabled: bool,
        jitter_seconds: int = 300,
        limit: int = 100,
        rotations_paused: bool = False,
    ) -> dict[str, int]:
        """Queue scheduled rotations and verifies (nothing while rotation is switched off).
        ``rotations_paused`` (DR lag, HA_DR.md §6.1): verifies only, no rotations."""
        if not enabled:
            return {"rotations": 0, "verifies": 0}
        now = utcnow()
        rotations = verifies = 0
        due = [] if rotations_paused else await self._accounts.due_for_rotation(now, limit)
        for account in due:
            policy = await self._accounts.safe_policy(account.safe_id)
            if not in_window(policy.maintenance_window if policy else None, now):
                continue
            at = now + timedelta(seconds=secrets.randbelow(max(jitter_seconds, 0) + 1))
            rotations += await self._enqueue(account.id, account.safe_id, SCHEDULE, at)
        for account in await self._accounts.due_for_verify(now, limit):
            verifies += await self._enqueue(account.id, account.safe_id, VERIFY, now)
        await self._jobs.commit()
        return {"rotations": rotations, "verifies": verifies}

    async def scan_empty_passwords(self, limit: int = 200) -> int:
        """Flag stored passwords that are empty; each secret version is looked at once."""
        flagged = 0
        for account in await self._accounts.unscanned(limit):
            value = await self._vault.read(
                owner_type=ACCOUNT_SECRET, owner_id=account.id, version=account.secret_version
            )
            flags = [f for f in account.risk_flags if f != HIGH_RISK_EMPTY_PASSWORD]
            if value.strip() == "":
                flags.append(HIGH_RISK_EMPTY_PASSWORD)
                flagged += 1
            await self._accounts.update(
                account.id, {"risk_flags": flags, "risk_checked_version": account.secret_version}
            )
            if HIGH_RISK_EMPTY_PASSWORD in flags and (
                HIGH_RISK_EMPTY_PASSWORD not in account.risk_flags
            ):
                await flag_empty(
                    self._alerts, self._audit, account.id, account.safe_id, account.username
                )
        await self._jobs.commit()
        return flagged


async def flag_empty(
    alerts: AlertService,
    audit: AuditService,
    account_id: uuid.UUID,
    safe_id: uuid.UUID,
    username: str,
) -> None:
    """Alert and audit a high-risk empty password (the caller sets the flag and commits)."""
    await alerts.raise_alert(
        SYSTEM_ACTOR,
        kind="account.high_risk_empty_password",
        message=f"Account {username} has an empty password (high risk)",
        object_type="account",
        object_id=account_id,
        details={"account_id": str(account_id), "safe_id": str(safe_id)},
    )
    await audit.record(
        SYSTEM_ACTOR,
        "account.high_risk_empty_password",
        object_type="account",
        object_id=account_id,
        safe_id=safe_id,
        outcome="failure",
    )
