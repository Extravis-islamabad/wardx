"""The rotation store's verify outcomes and side effects (split from rotation_store.py).

Mixed into RotationStore: these methods use its repositories, audit and alert helpers.
"""

from __future__ import annotations

from typing import Any

from src.contracts.dto.rotation.rotation_dto import (
    CONFIRMED_UNTRUSTWORTHY,
    FAILED,
    HIGH_RISK_EMPTY_PASSWORD,
    IN_SYNC,
    PENDING,
    RECONCILE,
    SUCCEEDED,
    UNVERIFIED,
    VERIFY_UNTRUSTWORTHY,
    RotationContextDTO,
)
from src.core.context import SYSTEM_ACTOR
from src.models import utcnow
from src.rotation.drivers.base import StepResult

MEDIUM = "medium"
_CLEAR_RISK = {"risk_accepted_by": None, "risk_accepted_at": None, "risk_accepted_reason": None}


def next_sync(previous: str, new: str) -> str:
    """An accepted risk (confirmed_untrustworthy) is cleared only by a clean verify;
    an inconclusive or unreachable verify leaves it listed."""
    if previous == CONFIRMED_UNTRUSTWORTHY and new in (UNVERIFIED, "unreachable"):
        return CONFIRMED_UNTRUSTWORTHY
    return new


class RotationOutcomesMixin:
    async def verify_finished(
        self,
        ctx: RotationContextDTO,
        sync_status: str,
        verify_result: str | None,
        *,
        steps: list[tuple[str, StepResult, int | None]],
        detail: str | None = None,
    ) -> None:
        """A verify-only (or dry-run) job's result on the account's sync state."""
        for s in steps:
            await self._step(ctx.job.id, *s)
        account = await self._accounts.get(ctx.account.id, lock=True)
        now = utcnow()
        new_sync = next_sync(account.sync_status, sync_status)
        changes: dict[str, Any] = {"sync_status": new_sync, "last_verify_attempt_at": now}
        if sync_status == "unreachable":
            changes["unreachable_count"] = account.unreachable_count + 1
            # An earlier conclusion stands; unreachable only says "no conclusion now".
            if account.sync_status in (IN_SYNC, "out_of_sync", UNVERIFIED):
                changes["sync_status"] = account.sync_status
        else:
            changes["unreachable_count"] = 0
        if sync_status == IN_SYNC:
            changes |= {"last_verified_at": now, "last_verify_method": "login", **_CLEAR_RISK}
        await self._accounts.update(ctx.account.id, changes)
        await self._risk_cleared(ctx, account.sync_status, changes["sync_status"])
        ok = sync_status == IN_SYNC
        await self._jobs.update(
            ctx.job.id,
            {
                "status": SUCCEEDED if ok else FAILED,
                "verify_result": verify_result,
                "finished_at": now,
                "lease_until": None,
                "detail": detail or sync_status,
            },
        )
        await self._audit_job(
            ctx,
            "rotation.verify",
            outcome="success" if ok else "failure",
            sync_status=sync_status,
            verify_result=verify_result,
            dry_run=ctx.job.dry_run,
        )
        who = f"{ctx.account.username}@{ctx.target.name}"
        if sync_status == "out_of_sync":
            await self._alert(ctx, "rotation.out_of_sync", f"{who} rejected its vaulted password")
        elif sync_status == VERIFY_UNTRUSTWORTHY:
            await self._audit_job(ctx, "rotation.verify_untrustworthy", outcome="failure")
            await self._alert(
                ctx,
                "rotation.verify_untrustworthy",
                f"{who} accepted a wrong password during verify; normal access is blocked "
                "until an administrator confirms or reconciles it.",
            )
        elif changes.get("unreachable_count") == 3:
            await self._alert(
                ctx, "rotation.unreachable", f"{who} was unreachable 3 times in a row", MEDIUM
            )
        await self._jobs.commit()

    async def _risk_cleared(self, ctx: RotationContextDTO, before: str, after: str) -> None:
        if before == CONFIRMED_UNTRUSTWORTHY and after == IN_SYNC:
            await self._audit.record(
                SYSTEM_ACTOR,
                "rotation.accepted_risk_cleared",
                object_type="account",
                object_id=ctx.account.id,
                safe_id=ctx.account.safe_id,
                details={"job_id": str(ctx.job.id), "reason": "clean verify"},
            )

    async def flag_empty_password(
        self,
        ctx: RotationContextDTO,
        *,
        on_device: bool = False,
        steps: list[tuple[str, StepResult, int | None]] = (),
        candidate: int | None = None,
    ) -> None:
        """The vaulted password (or, ``on_device``, the device's password) is empty: flag
        the account high risk and stop. A stored candidate is kept, labelled abandoned."""
        for s in steps:
            await self._step(ctx.job.id, *s)
        if HIGH_RISK_EMPTY_PASSWORD not in ctx.account.risk_flags:
            await self._accounts.update(
                ctx.account.id,
                {"risk_flags": [*ctx.account.risk_flags, HIGH_RISK_EMPTY_PASSWORD]},
            )
        where = "device accepted an empty password" if on_device else "vaulted password is empty"
        await self.fail(
            ctx,
            f"The {where} (high_risk_empty_password)",
            candidate=candidate,
            alert=(
                "account.high_risk_empty_password",
                f"{ctx.account.username}@{ctx.target.name} has an empty password (high risk)",
            ),
        )

    async def audit_reconcile_account_use(self, ctx: RotationContextDTO) -> None:
        """Using the reconcile account is audited; it is not a check-out."""
        if ctx.reconcile is None:
            return
        await self._audit.record(
            SYSTEM_ACTOR,
            "rotation.reconcile_account_used",
            object_type="account",
            object_id=ctx.reconcile.id,
            safe_id=ctx.reconcile.safe_id,
            details={"job_id": str(ctx.job.id), "for_account_id": str(ctx.account.id)},
        )
        await self._jobs.commit()

    async def enqueue_auto_reconcile(self, ctx: RotationContextDTO) -> None:
        """Out of sync and the safe reconciles automatically: queue a reconcile (alerted)."""
        if not (ctx.policy.auto_reconcile and ctx.account.reconcile_account_id):
            return
        if await self._jobs.open_for_account(ctx.account.id) is not None:
            return
        await self._jobs.create(
            {
                "account_id": ctx.account.id,
                "target_id": ctx.target.id,
                "reason": RECONCILE,
                "status": PENDING,
                "note": "auto-reconcile after out_of_sync",
            }
        )
        await self._audit_job(ctx, "rotation.auto_reconcile_queued")
        await self._jobs.commit()
