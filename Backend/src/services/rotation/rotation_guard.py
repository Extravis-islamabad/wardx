"""Where rotation meets access: what it blocks, and the after-use trigger.

- While an account has a rotation waiting for release or in progress (or one that
  needs attention), or its last verify was untrustworthy, NEW normal check-outs and
  gateway sessions are refused with a 409 that says why. Emergency (break-glass)
  check-outs are never blocked here: they extend the wait and count as holders.
- When a check-out ends (check-in, expiry, revoke) on an account whose policy rotates
  after use, a job is created at once in ``waiting_release``; it runs only when every
  holder has released the account.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from src.contracts.dto.rotation.rotation_dto import (
    AFTER_USE,
    BLOCKING_STATES,
    NEEDS_ATTENTION,
    VERIFY_UNTRUSTWORTHY,
    WAITING_RELEASE,
)
from src.core.context import SYSTEM_ACTOR
from src.errors.exceptions import ConflictError
from src.models import utcnow
from src.repositories.rotation.rotation_account_repository import RotationAccountRepository
from src.repositories.rotation.rotation_job_repository import RotationJobRepository
from src.services.audit.audit_service import AuditService


class RotationPending(ConflictError):
    code = "rotation_pending"


class VerifyUntrustworthy(ConflictError):
    code = "verify_untrustworthy"


class RotationGuard:
    def __init__(
        self,
        jobs: RotationJobRepository,
        accounts: RotationAccountRepository,
        audit: AuditService,
    ) -> None:
        self._jobs = jobs
        self._accounts = accounts
        self._audit = audit

    async def ensure_normal_access(self, account_id: uuid.UUID) -> None:
        """Refuse a new normal check-out or gateway session while rotation holds it."""
        account = await self._accounts.get(account_id)
        if account is not None and account.sync_status == VERIFY_UNTRUSTWORTHY:
            raise VerifyUntrustworthy(
                "This account's last verify was untrustworthy (the device accepted a wrong "
                "password). Normal access is blocked until an administrator confirms or "
                "reconciles it; break-glass still works."
            )
        job = await self._jobs.open_for_account(account_id)
        if job is None or job.status not in BLOCKING_STATES:
            return
        if job.status == WAITING_RELEASE:
            message = (
                "Rotation pending: this account's password rotates once every holder has "
                "released it, so new check-outs and sessions wait until then"
            )
        elif job.status == NEEDS_ATTENTION:
            message = "A rotation of this account needs an administrator's attention"
        else:
            message = "This account's password is being rotated right now; try again shortly"
        raise RotationPending(message, {"job_id": str(job.id), "rotation_status": job.status})

    async def after_use(self, account_ids: Iterable[uuid.UUID]) -> list[uuid.UUID]:
        """Queue rotate-after-use jobs (waiting for release) in the caller's transaction."""
        created: list[uuid.UUID] = []
        for account in await self._accounts.accounts_with_safe(sorted(set(account_ids), key=str)):
            policy = await self._accounts.safe_policy(account.safe_id)
            if not (account.rotate_after_use or (policy and policy.rotate_after_use)):
                continue
            if account.secret_type != "password" or not account.secret_version:
                continue
            if await self._jobs.open_for_account(account.id) is not None:
                continue
            now = utcnow()
            try:
                job_id = await self._jobs.create(
                    {
                        "account_id": account.id,
                        "target_id": await self._accounts.target_id_of(account.id),
                        "reason": AFTER_USE,
                        "status": WAITING_RELEASE,
                        "waiting_since": now,
                        "not_before": now,
                    }
                )
            except ConflictError:
                continue  # another job opened concurrently; it covers this use
            await self._accounts.update(account.id, {"rotation_status": WAITING_RELEASE})
            await self._audit.record(
                SYSTEM_ACTOR,
                "rotation.queued",
                object_type="rotation_job",
                object_id=job_id,
                safe_id=account.safe_id,
                details={"account_id": str(account.id), "reason": AFTER_USE},
            )
            created.append(job_id)
        return created
