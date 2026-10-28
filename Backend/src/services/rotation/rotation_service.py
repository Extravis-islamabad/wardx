"""On-demand rotation requests and what the console reads about rotation.

Rules:
- Rotate, Verify and Reconcile need ``manage_accounts`` on the account's safe and a
  reason; each request is audited. Nothing is queued while either safety switch is
  off, on a Telnet target (non-rotatable), or without a pinned host key: the refusal
  says why, and nothing connects.
- Reading an account's rotation, or a job, needs ``list`` on its safe; the job list
  shows jobs of accounts in safes the caller can list.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from typing import Any

from src.contracts.dto.rotation.rotation_dto import (
    MANUAL,
    PENDING,
    RECONCILE,
    VERIFY,
    VERIFY_UNTRUSTWORTHY,
    RotationAccountDTO,
    RotationAttentionDTO,
    RotationFilterDTO,
    RotationJobDTO,
    RotationTargetDTO,
    SafeRotationPolicyDTO,
)
from src.core.config import Settings
from src.core.context import Actor
from src.core.enums import Protocol, SafePermission
from src.errors.exceptions import AppError, ConflictError, NotFoundError
from src.models import utcnow
from src.repositories.rotation.rotation_account_repository import RotationAccountRepository
from src.repositories.rotation.rotation_job_repository import RotationJobRepository
from src.rotation import policy as policies
from src.rotation.drivers.registry import default_registry
from src.services.audit.audit_service import AuditService
from src.services.inventory.account_service import AccountService

OPERATIONS = {"rotate": MANUAL, "verify": VERIFY, "reconcile": RECONCILE}
TELNET = "non-rotatable (Telnet)"


class RotationRefused(AppError):
    status_code = 409
    code = "rotation_refused"


def non_rotatable_reason(protocol: str, platform: str) -> str | None:
    """Why a target can never be rotated, whatever its switches (shown in the UI)."""
    if protocol == Protocol.TELNET:
        return TELNET
    driver = default_registry().get(platform)
    if driver is None:
        return f"no rotation driver for {platform} yet"
    if protocol not in getattr(driver, "protocols", {Protocol.SSH}):
        return f"the {platform} driver does not rotate over {protocol}"
    return None


@dataclass(frozen=True)
class AccountRotationView:
    account: RotationAccountDTO
    target: RotationTargetDTO
    safe_policy: SafeRotationPolicyDTO
    effective_policy: dict[str, Any] | None
    policy_error: str | None
    effective_interval_days: int | None
    effective_rotate_after_use: bool
    non_rotatable_reason: str | None
    open_job: RotationJobDTO | None
    jobs: list[RotationJobDTO]


class RotationService:
    def __init__(
        self,
        jobs: RotationJobRepository,
        accounts: RotationAccountRepository,
        account_service: AccountService,
        audit: AuditService,
        settings: Settings,
    ) -> None:
        self._jobs = jobs
        self._accounts = accounts
        self._account_service = account_service
        self._audit = audit
        self._settings = settings

    async def request(
        self,
        actor: Actor,
        account_id: uuid.UUID,
        operation: str,
        note: str,
        *,
        dry_run: bool = False,
    ) -> RotationJobDTO:
        reason = OPERATIONS[operation]
        visible = await self._account_service.get(account_id, lock=True)
        await self._account_service.authorise(actor, visible, SafePermission.MANAGE_ACCOUNTS)
        note = (note or "").strip()
        if len(note) < 3:
            raise ConflictError("Give a reason (at least 3 characters)")
        account = await self._accounts.get(account_id)
        target = await self._accounts.target_of(account_id)
        why = self._refusal(account, target, reason)
        if why:
            raise RotationRefused(why)
        job_id = await self._jobs.create(
            {
                "account_id": account.id,
                "target_id": target.id,
                "reason": reason,
                "status": PENDING,
                "not_before": utcnow(),
                "requested_by": actor.id,
                "note": note,
                "dry_run": dry_run and reason != VERIFY,
            }
        )
        if reason != VERIFY:
            await self._accounts.update(account.id, {"rotation_status": PENDING})
        await self._audit.record(
            actor,
            f"rotation.request_{operation}",
            object_type="rotation_job",
            object_id=job_id,
            safe_id=account.safe_id,
            details={"account_id": str(account.id), "reason": note, "dry_run": dry_run},
        )
        await self._jobs.commit()
        return await self._jobs.get(job_id)

    def _refusal(
        self, account: RotationAccountDTO, target: RotationTargetDTO, reason: str
    ) -> str | None:
        fixed = non_rotatable_reason(target.protocol, target.platform)
        if fixed:
            return f"{target.name} is {fixed}"
        if not self._settings.rotation_enabled:
            return "Rotation is switched off on this WardX instance (WARDX_ROTATION_ENABLED)"
        if not target.rotation_allowed:
            return f"Rotation is not allowed on target {target.name} (rotation_allowed is off)"
        if not target.is_active:
            return f"Target {target.name} is inactive"
        if target.protocol == Protocol.SSH and not target.ssh_host_key:
            return f"{target.name} has no pinned SSH host key; learn or pin it first"
        if account.secret_type != "password":
            return "Only passwords are rotated (SSH keys come later)"
        if reason == RECONCILE:
            if account.reconcile_account_id is None:
                return "Link a reconcile account to this account first"
        elif not account.secret_version:
            return "No secret is stored for this account"
        if reason == VERIFY and account.sync_status == VERIFY_UNTRUSTWORTHY:
            return "The last verify was untrustworthy: confirm or reconcile the account instead"
        return None

    async def account_rotation(self, actor: Actor, account_id: uuid.UUID) -> AccountRotationView:
        visible = await self._account_service.get_visible(actor, account_id)
        account = await self._accounts.get(visible.id)
        target = await self._accounts.target_of(visible.id)
        safe_policy = await self._accounts.safe_policy(account.safe_id)
        effective, error = None, None
        try:
            effective = policies.resolve(
                target.platform, target.policy_overrides, account.password_length
            ).as_dict()
        except policies.PolicyError as exc:
            error = str(exc)
        intervals = [
            i for i in (account.rotation_interval_days, safe_policy.rotation_interval_days) if i
        ]
        jobs, _ = await self._jobs.list(
            RotationFilterDTO(account_id=account.id), page=1, page_size=20
        )
        return AccountRotationView(
            account=account,
            target=target,
            safe_policy=safe_policy,
            effective_policy=effective,
            policy_error=error,
            effective_interval_days=min(intervals) if intervals else None,
            effective_rotate_after_use=account.rotate_after_use or safe_policy.rotate_after_use,
            non_rotatable_reason=non_rotatable_reason(target.protocol, target.platform),
            open_job=await self._jobs.open_for_account(account.id),
            jobs=jobs,
        )

    async def list_jobs(
        self, actor: Actor, filters: RotationFilterDTO, *, page: int, page_size: int
    ) -> tuple[list[RotationJobDTO], int]:
        visible = await self._account_service.listable_safe_ids(actor)
        return await self._jobs.list(
            replace(filters, safe_ids=visible), page=page, page_size=page_size
        )

    async def get_job(self, actor: Actor, job_id: uuid.UUID) -> RotationJobDTO:
        job = await self._jobs.get(job_id, with_steps=True)
        if job is None:
            raise NotFoundError("Rotation job not found")
        await self._account_service.get_visible(actor, job.account_id)
        return job

    async def attention(self, actor: Actor) -> RotationAttentionDTO:
        visible = await self._account_service.listable_safe_ids(actor)
        attention, _ = await self._jobs.list(
            RotationFilterDTO(status="needs_attention", safe_ids=visible), page=1, page_size=100
        )
        waiting, _ = await self._jobs.list(
            RotationFilterDTO(status="waiting_release", safe_ids=visible), page=1, page_size=100
        )
        out_of_sync, untrustworthy, confirmed, empty = await self._accounts.attention_accounts(
            visible
        )
        return RotationAttentionDTO(
            needs_attention=attention,
            out_of_sync=out_of_sync,
            untrustworthy=untrustworthy,
            confirmed_untrustworthy=confirmed,
            empty_password=empty,
            release_overdue=[j for j in waiting if j.release_alerted_at is not None],
        )
