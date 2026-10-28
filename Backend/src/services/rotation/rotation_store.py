"""The rotation engine's database side: each method is one committed unit of work.

The engine (rotation_engine.py) never holds a transaction open while it talks to a
device: it calls one of these methods, which commits the new state (with its audit
event and any alert) before the engine's next device step.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from src.contracts.dto.rotation.rotation_dto import (
    CANDIDATE_STORED,
    CHANGED_UNVERIFIED,
    FAILED,
    HIGH_RISK_EMPTY_PASSWORD,
    IN_SYNC,
    INCONCLUSIVE,
    NEEDS_ATTENTION,
    RECONCILE,
    SUCCEEDED,
    UNTRUSTWORTHY,
    UNVERIFIED,
    VERIFIED,
    VERIFY_UNTRUSTWORTHY,
    WAITING_RELEASE,
    RotationContextDTO,
)
from src.core.context import SYSTEM_ACTOR
from src.models import utcnow
from src.repositories.rotation.rotation_account_repository import RotationAccountRepository
from src.repositories.rotation.rotation_job_repository import RotationJobRepository
from src.rotation.drivers.base import Identity, StepResult
from src.services.audit.audit_service import AuditService
from src.services.inventory.account_service import ACCOUNT_SECRET
from src.services.rotation.rotation_outcomes import _CLEAR_RISK, RotationOutcomesMixin, next_sync
from src.services.security.alert_service import AlertService
from src.services.sessions.host_key_service import HostKeyService
from src.services.sessions.tls_cert_service import TlsCertService
from src.services.vault.vault_service import VaultService

SYNC_FOR = {VERIFIED: IN_SYNC, UNTRUSTWORTHY: VERIFY_UNTRUSTWORTHY, INCONCLUSIVE: UNVERIFIED}


class RotationStore(RotationOutcomesMixin):
    async def record_host_key_mismatch(
        self,
        ctx: RotationContextDTO,
        presented: str | None,
        *,
        source: str,
        identity: Identity = Identity.SSH,
    ) -> None:
        """The target presented another host key (or API-SSL certificate): record it on
        the target, which blocks every later rotation and verify there until an
        administrator accepts one."""
        if identity == Identity.TLS:
            if self._tls_certs is not None:
                await self._tls_certs.record_mismatch(
                    SYSTEM_ACTOR, ctx.target.id, presented=presented, source=source
                )
        elif self._host_keys is not None:
            await self._host_keys.record_mismatch(
                SYSTEM_ACTOR, ctx.target.id, presented=presented, source=source
            )

    def __init__(
        self,
        jobs: RotationJobRepository,
        accounts: RotationAccountRepository,
        vault: VaultService,
        audit: AuditService,
        alerts: AlertService,
        *,
        host_keys: HostKeyService | None = None,
        tls_certs: TlsCertService | None = None,
        lease_seconds: int = 600,
    ) -> None:
        self._host_keys = host_keys
        self._tls_certs = tls_certs
        self._jobs = jobs
        self._accounts = accounts
        self._vault = vault
        self._audit = audit
        self._alerts = alerts
        self._lease = timedelta(seconds=lease_seconds)

    # ── Reading ──

    async def context(self, job_id: uuid.UUID) -> RotationContextDTO | None:
        job = await self._jobs.get(job_id)
        if job is None:
            return None
        account = await self._accounts.get(job.account_id)
        target = await self._accounts.target_of(job.account_id)
        policy = await self._accounts.safe_policy(account.safe_id)
        reconcile = None
        if account.reconcile_account_id is not None:
            reconcile = await self._accounts.get(account.reconcile_account_id)
        await self._jobs.rollback()
        return RotationContextDTO(job, account, target, policy, reconcile)

    async def account_of_job(self, job_id: uuid.UUID) -> uuid.UUID | None:
        try:
            return await self._jobs.account_of(job_id)
        finally:
            await self._jobs.rollback()

    async def read_secret(self, account_id: uuid.UUID, version: int) -> str:
        try:
            return await self._vault.read(
                owner_type=ACCOUNT_SECRET, owner_id=account_id, version=version
            )
        finally:
            await self._jobs.rollback()

    # ── Job state ──

    async def _audit_job(
        self, ctx: RotationContextDTO, action: str, outcome: str = "success", **details: Any
    ) -> None:
        await self._audit.record(
            SYSTEM_ACTOR,
            action,
            object_type="rotation_job",
            object_id=ctx.job.id,
            outcome=outcome,
            safe_id=ctx.account.safe_id,
            details={
                "account_id": str(ctx.account.id),
                "reason": ctx.job.reason,
                **details,
            },
        )

    async def _alert(
        self, ctx: RotationContextDTO, kind: str, message: str, severity: str = "high"
    ) -> None:
        await self._alerts.raise_alert(
            SYSTEM_ACTOR,
            kind=kind,
            severity=severity,
            message=message,
            object_type="account",
            object_id=ctx.account.id,
            details={
                "job_id": str(ctx.job.id),
                "account_id": str(ctx.account.id),
                "safe_id": str(ctx.account.safe_id),
                "target": ctx.target.name,
                "username": ctx.account.username,
            },
        )

    async def _step(
        self, job_id: uuid.UUID, step: str, result: StepResult | None, version: int | None
    ) -> None:
        if result is None:
            return
        await self._jobs.add_step(
            {
                "job_id": job_id,
                "step": step,
                "outcome": str(result.outcome),
                "secret_version": version,
                "detail": result.detail[:2000] if result.detail else None,
                "transcript": result.transcript or None,
                "channel": result.channel,
            }
        )

    async def step(
        self, job_id: uuid.UUID, step: str, result: StepResult, version: int | None = None
    ) -> None:
        await self._step(job_id, step, result, version)
        await self._jobs.commit()

    async def advance(
        self,
        job_id: uuid.UUID,
        status: str,
        *,
        step: tuple[str, StepResult, int | None] | None = None,
        **changes: Any,
    ) -> None:
        """Commit the job's next state (and renew its lease) before the next device step."""
        if step is not None:
            await self._step(job_id, *step)
        await self._jobs.update(
            job_id, {"status": status, "lease_until": utcnow() + self._lease, **changes}
        )
        await self._jobs.commit()

    async def wait_for_release(self, ctx: RotationContextDTO) -> dict[str, int] | None:
        """Holders of the account, if any: the job then waits (and nothing was touched)."""
        await self._accounts.get(ctx.account.id, lock=True)
        holders = await self._accounts.holders(ctx.account.id)
        if not any(holders.values()):
            await self._jobs.rollback()
            return None
        await self._jobs.update(
            ctx.job.id,
            {
                "status": WAITING_RELEASE,
                "waiting_since": ctx.job.waiting_since or utcnow(),
                "lease_until": None,
                "candidate_version": None,
                "change_sent_at": None,
            },
        )
        await self._accounts.update(ctx.account.id, {"rotation_status": WAITING_RELEASE})
        await self._audit_job(ctx, "rotation.waiting_release", **holders)
        await self._jobs.commit()
        return holders

    async def store_candidate(
        self, ctx: RotationContextDTO, secret: str, driver: str
    ) -> tuple[int, int]:
        """Step 2: store C as version N+1 (status candidate) and commit candidate_stored."""
        account = await self._accounts.get(ctx.account.id, lock=True)
        current = account.secret_version
        version = await self._vault.next_version(ACCOUNT_SECRET, account.id)
        await self._vault.store(
            owner_type=ACCOUNT_SECRET,
            owner_id=account.id,
            version=version,
            plaintext=secret,
            created_by=None,
            status="candidate",
        )
        await self._jobs.update(
            ctx.job.id,
            {
                "status": CANDIDATE_STORED,
                "from_version": current,
                "candidate_version": version,
                "secret_versions_touched": sorted({current, version} - {0}),
                "driver": driver,
                "change_sent_at": None,
                "lease_until": utcnow() + self._lease,
            },
        )
        await self._accounts.update(account.id, {"rotation_status": "running"})
        await self._jobs.add_step(
            {
                "job_id": ctx.job.id,
                "step": "store_candidate",
                "outcome": "ok",
                "secret_version": version,
                "detail": f"candidate stored as version {version}; current stays {current}",
            }
        )
        await self._jobs.commit()
        return current, version

    async def mark_change_sent(self, ctx: RotationContextDTO, candidate: int | None) -> bool:
        """Commit that the change is about to be sent; False (and wait) if holders appeared."""
        await self._accounts.get(ctx.account.id, lock=True)
        holders = await self._accounts.holders(ctx.account.id)
        if any(holders.values()):
            if candidate:
                await self._vault.label(ACCOUNT_SECRET, ctx.account.id, candidate, "abandoned")
            await self._jobs.update(
                ctx.job.id,
                {
                    "status": WAITING_RELEASE,
                    "waiting_since": utcnow(),
                    "lease_until": None,
                    "candidate_version": None,
                },
            )
            await self._accounts.update(ctx.account.id, {"rotation_status": WAITING_RELEASE})
            await self._audit_job(ctx, "rotation.waiting_release", **holders)
            await self._jobs.commit()
            return False
        await self._jobs.update(
            ctx.job.id, {"change_sent_at": utcnow(), "lease_until": utcnow() + self._lease}
        )
        await self._jobs.commit()
        return True

    async def reschedule(
        self,
        ctx: RotationContextDTO,
        status: str,
        delay_seconds: int,
        detail: str,
        *,
        step: tuple[str, StepResult, int | None] | None = None,
        **changes: Any,
    ) -> None:
        if step is not None:
            await self._step(ctx.job.id, *step)
        await self._jobs.update(
            ctx.job.id,
            {
                "status": status,
                "not_before": utcnow() + timedelta(seconds=delay_seconds),
                "lease_until": None,
                "detail": detail[:2000],
                **changes,
            },
        )
        await self._jobs.commit()

    async def fail(
        self,
        ctx: RotationContextDTO,
        detail: str,
        *,
        candidate: int | None = None,
        sync_status: str | None = None,
        alert: tuple[str, str] | None = None,
        step: tuple[str, StepResult, int | None] | None = None,
        status: str = FAILED,
    ) -> None:
        """End the job without promoting. The candidate is labelled abandoned (kept)."""
        if step is not None:
            await self._step(ctx.job.id, *step)
        if candidate:
            await self._vault.label(ACCOUNT_SECRET, ctx.account.id, candidate, "abandoned")
        await self._jobs.update(
            ctx.job.id,
            {"status": status, "finished_at": utcnow(), "lease_until": None, "detail": detail},
        )
        changes: dict[str, Any] = {
            "rotation_status": NEEDS_ATTENTION if status == NEEDS_ATTENTION else "idle",
        }
        if ctx.job.reason != "verify" and not ctx.job.dry_run:
            changes["last_rotation_status"] = status
        if sync_status:
            changes["sync_status"] = sync_status
        await self._accounts.update(ctx.account.id, changes)
        await self._audit_job(
            ctx,
            "rotation.needs_attention" if status == NEEDS_ATTENTION else "rotation.failed",
            outcome="failure",
            detail=detail,
        )
        if alert is not None:
            await self._alert(ctx, *alert)
        await self._jobs.commit()

    async def needs_attention(
        self,
        ctx: RotationContextDTO,
        detail: str,
        *,
        step: tuple[str, StepResult, int | None] | None = None,
    ) -> None:
        """Both versions kept; automatic retries stop until an administrator resolves it."""
        await self.fail(
            ctx,
            detail,
            step=step,
            status=NEEDS_ATTENTION,
            alert=(
                "rotation.needs_attention",
                f"Rotation of {ctx.account.username}@{ctx.target.name} needs attention: {detail}",
            ),
        )

    async def promote(
        self,
        ctx: RotationContextDTO,
        candidate: int,
        verify_result: str,
        *,
        steps: list[tuple[str, StepResult, int | None]],
    ) -> None:
        """Step 7: the candidate becomes current. Unverified unless the negative check held."""
        for s in steps:
            await self._step(ctx.job.id, *s)
        before = await self._accounts.get(ctx.account.id, lock=True)
        now = utcnow()
        await self._vault.label(ACCOUNT_SECRET, ctx.account.id, candidate, "current")
        verified = verify_result == VERIFIED
        sync = next_sync(before.sync_status, SYNC_FOR[verify_result])
        changes: dict[str, Any] = {
            "secret_version": candidate,
            "secret_updated_at": now,
            "last_rotated_at": now,
            "rotation_status": "idle",
            "sync_status": sync,
            "unreachable_count": 0,
            "last_rotation_status": SUCCEEDED if verified else CHANGED_UNVERIFIED,
            "risk_flags": [f for f in ctx.account.risk_flags if f != HIGH_RISK_EMPTY_PASSWORD],
            "risk_checked_version": candidate,
            "last_verify_attempt_at": now,
        }
        if verified:
            changes |= {"last_verified_at": now, "last_verify_method": "login", **_CLEAR_RISK}
        await self._accounts.update(ctx.account.id, changes)
        await self._risk_cleared(ctx, before.sync_status, sync)
        status = SUCCEEDED if verified else CHANGED_UNVERIFIED
        await self._jobs.update(
            ctx.job.id,
            {
                "status": status,
                "verify_result": verify_result,
                "finished_at": now,
                "lease_until": None,
                "detail": None if verified else f"changed, unverified ({verify_result})",
            },
        )
        action = "rotation.reconcile" if ctx.job.reason == RECONCILE else "rotation.succeeded"
        await self._audit_job(
            ctx,
            action if verified else "rotation.changed_unverified",
            from_version=ctx.job.from_version,
            new_version=candidate,
            verify_result=verify_result,
        )
        if verify_result == UNTRUSTWORTHY:
            await self._audit_job(ctx, "rotation.verify_untrustworthy", outcome="failure")
            await self._alert(
                ctx,
                "rotation.verify_untrustworthy",
                f"{ctx.account.username}@{ctx.target.name} accepted a wrong password during "
                "verify; the new password is stored but unverified. Normal access is blocked "
                "until an administrator confirms or reconciles it.",
            )
        await self._jobs.commit()
