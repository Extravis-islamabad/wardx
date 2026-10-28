"""An administrator's review of rotation trouble.

- ``resolve``: a job in needs_attention. The administrator says what is on the device:
  the current version (keep_current), the candidate (use_candidate), a value they set
  by hand (set_secret), or asks for a reconcile. Automatic retries resume only after.
- ``confirm``: an account whose verify was untrustworthy (the device accepted a wrong
  password). Confirming accepts that known risk with a written reason (20+ characters):
  the account becomes confirmed_untrustworthy, its alert is acknowledged and normal
  access returns, but it stays on the dashboard until a later clean verify. The
  confirming administrator must not be the one who requested that rotation.

Both need ``manage_accounts`` on the account's safe, a note, and are audited.
"""

from __future__ import annotations

import uuid

from src.contracts.dto.rotation.rotation_dto import (
    CONFIRMED_UNTRUSTWORTHY,
    HIGH_RISK_EMPTY_PASSWORD,
    NEEDS_ATTENTION,
    PENDING,
    RECONCILE,
    RESOLVED,
    UNVERIFIED,
    VERIFY_UNTRUSTWORTHY,
    RotationJobDTO,
)
from src.core.context import Actor
from src.core.enums import SafePermission
from src.errors.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.models import utcnow
from src.repositories.rotation.rotation_account_repository import RotationAccountRepository
from src.repositories.rotation.rotation_job_repository import RotationJobRepository
from src.repositories.security.alert_repository import AlertRepository
from src.services.audit.audit_service import AuditService
from src.services.inventory.account_service import ACCOUNT_SECRET, AccountService
from src.services.vault.vault_service import VaultService

# Same rule as break-glass: accepting a known risk needs a real explanation.
MIN_CONFIRM_REASON = 20
RESOLUTIONS = ("keep_current", "use_candidate", "set_secret", "reconcile")


class RotationReviewService:
    def __init__(
        self,
        jobs: RotationJobRepository,
        accounts: RotationAccountRepository,
        account_service: AccountService,
        vault: VaultService,
        alerts: AlertRepository,
        audit: AuditService,
    ) -> None:
        self._jobs = jobs
        self._accounts = accounts
        self._account_service = account_service
        self._vault = vault
        self._alerts = alerts
        self._audit = audit

    async def _manageable(self, actor: Actor, account_id: uuid.UUID) -> None:
        account = await self._account_service.get(account_id, lock=True)
        await self._account_service.authorise(actor, account, SafePermission.MANAGE_ACCOUNTS)

    @staticmethod
    def _note(note: str | None) -> str:
        note = (note or "").strip()
        if len(note) < 3:
            raise ConflictError("Give a note (at least 3 characters)")
        return note

    async def _ack(self, actor: Actor, kind: str, account_id: uuid.UUID) -> None:
        for alert_id in await self._alerts.open_ids_for(kind, account_id):
            await self._alerts.acknowledge(alert_id, actor.id, utcnow())
            await self._audit.record(
                actor,
                "alert.acknowledge",
                object_type="alert",
                object_id=alert_id,
                details={"kind": kind, "account_id": str(account_id)},
            )

    async def resolve(
        self,
        actor: Actor,
        job_id: uuid.UUID,
        action: str,
        note: str | None,
        secret: str | None = None,
    ) -> RotationJobDTO:
        if action not in RESOLUTIONS:
            raise ConflictError(f"Resolution is one of {', '.join(RESOLUTIONS)}")
        job = await self._jobs.get(job_id)
        if job is None:
            raise NotFoundError("Rotation job not found")
        await self._manageable(actor, job.account_id)
        job = await self._jobs.get(job_id, lock=True)
        if job.status != NEEDS_ATTENTION:
            raise ConflictError(
                f"Only a job that needs attention is resolved (this is {job.status})"
            )
        note = self._note(note)
        account = await self._accounts.get(job.account_id, lock=True)
        now = utcnow()
        changes: dict = {"rotation_status": "idle"}
        details: dict = {"account_id": str(account.id), "action": action, "note": note}
        if action == "keep_current":
            if job.candidate_version:
                await self._vault.label(
                    ACCOUNT_SECRET, account.id, job.candidate_version, "abandoned"
                )
            changes["sync_status"] = UNVERIFIED
        elif action == "use_candidate":
            if not job.candidate_version:
                raise ConflictError("This job has no candidate version")
            await self._vault.label(ACCOUNT_SECRET, account.id, job.candidate_version, "current")
            changes |= {
                "secret_version": job.candidate_version,
                "secret_updated_at": now,
                "last_rotated_at": now,
                "sync_status": UNVERIFIED,
            }
            details["new_version"] = job.candidate_version
        elif action == "set_secret":
            if not secret or not secret.strip():
                raise ConflictError("Give the password that is now on the device")
            version = await self._vault.next_version(ACCOUNT_SECRET, account.id)
            await self._vault.store(
                owner_type=ACCOUNT_SECRET,
                owner_id=account.id,
                version=version,
                plaintext=secret,
                created_by=actor.id,
            )
            if job.candidate_version:
                await self._vault.label(
                    ACCOUNT_SECRET, account.id, job.candidate_version, "abandoned"
                )
            changes |= {
                "secret_version": version,
                "secret_updated_at": now,
                "sync_status": UNVERIFIED,
                "risk_flags": [f for f in account.risk_flags if f != HIGH_RISK_EMPTY_PASSWORD],
                "risk_checked_version": version,
            }
            details["new_version"] = version
        await self._jobs.update(
            job.id,
            {
                "status": RESOLVED,
                "resolution": action,
                "resolution_note": note,
                "resolved_by": actor.id,
                "resolved_at": now,
            },
        )
        await self._accounts.update(account.id, changes)
        if action == "reconcile":
            if account.reconcile_account_id is None:
                raise ConflictError("Link a reconcile account to this account first")
            reconcile_id = await self._jobs.create(
                {
                    "account_id": account.id,
                    "target_id": job.target_id,
                    "reason": RECONCILE,
                    "status": PENDING,
                    "requested_by": actor.id,
                    "note": note,
                }
            )
            details["reconcile_job_id"] = str(reconcile_id)
        await self._ack(actor, "rotation.needs_attention", account.id)
        await self._audit.record(
            actor,
            "rotation.resolve",
            object_type="rotation_job",
            object_id=job.id,
            safe_id=account.safe_id,
            details=details,
        )
        await self._jobs.commit()
        return await self._jobs.get(job.id, with_steps=True)

    async def confirm(self, actor: Actor, account_id: uuid.UUID, reason: str | None) -> None:
        """Accept the risk of an untrustworthy verify (written reason, audited).

        The account moves to confirmed_untrustworthy, not in_sync: normal access is
        allowed again, but it stays listed until a later clean verify clears it.
        """
        await self._manageable(actor, account_id)
        account = await self._accounts.get(account_id, lock=True)
        if account.sync_status != VERIFY_UNTRUSTWORTHY:
            raise ConflictError("Only an account whose verify was untrustworthy is confirmed")
        reason = (reason or "").strip()
        if len(reason) < MIN_CONFIRM_REASON:
            raise ConflictError(
                f"Confirming accepts a known risk: give a reason of at least "
                f"{MIN_CONFIRM_REASON} characters"
            )
        last = await self._jobs.latest_change_for_account(account_id)
        if last is not None and last.requested_by is not None and last.requested_by == actor.id:
            raise ForbiddenError(
                "You requested that rotation; another administrator must confirm it"
            )
        now = utcnow()
        await self._accounts.update(
            account_id,
            {
                "sync_status": CONFIRMED_UNTRUSTWORTHY,
                "last_verify_method": "attested",
                "risk_accepted_by": actor.id,
                "risk_accepted_at": now,
                "risk_accepted_reason": reason,
            },
        )
        await self._ack(actor, "rotation.verify_untrustworthy", account_id)
        await self._audit.record(
            actor,
            "rotation.verify_confirmed",
            object_type="account",
            object_id=account_id,
            safe_id=account.safe_id,
            details={
                "reason": reason,
                "version": account.secret_version,
                "job_id": str(last.id) if last else None,
            },
        )
        await self._jobs.commit()


__all__ = ["RECONCILE", "RESOLUTIONS", "RotationReviewService"]
