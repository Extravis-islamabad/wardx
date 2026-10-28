"""Verify-only runs and the device-side empty-password check (mixed into JobRun).

Split from rotation_run.py. ``empty_on_device`` runs only when the stored password was
just refused and the driver can probe emptiness without side effects (MikroTik: one
empty-password login over API-SSL). It takes the place of that run's single negative
check, which only follows an accepted login, so a run still makes at most one login
with a password WardX did not store.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.contracts.dto.rotation.rotation_dto import (
    IN_SYNC,
    OUT_OF_SYNC,
    UNREACHABLE,
    UNTRUSTWORTHY,
    UNVERIFIED,
    VERIFIED,
    VERIFY,
    VERIFY_UNTRUSTWORTHY,
)
from src.rotation.drivers.base import Capability, DriverError, Outcome, StepResult

if TYPE_CHECKING:
    from src.services.rotation.rotation_run import Step


class VerifyMixin:
    @staticmethod
    def negative_step(neg: StepResult, verdict: str) -> StepResult:
        """The negative check as recorded: its outcome and channel, never the password."""
        return StepResult(neg.outcome, f"wrong password {verdict}", channel=neg.channel)

    async def empty_on_device(self, steps: list[Step], *, candidate: int | None = None) -> bool:
        """The stored password was refused: is the device password empty? One probe, only
        for drivers that can tell without side effects. True (account flagged high risk,
        job stopped) when it is; False when it is not or the probe proves nothing."""
        if Capability.EMPTY_PROBE not in self.driver.capabilities:
            return False
        probe = await self.driver.probe_empty_password(
            self.target, self.account, self.e.driver_context(list(self._secrets.values()))
        )
        empty = probe.outcome == Outcome.OK
        verdict = "accepted: the device password is EMPTY" if empty else "refused"
        if probe.outcome not in (Outcome.OK, Outcome.AUTH_FAILED):
            verdict = f"inconclusive ({probe.outcome})"
        steps.append(
            (
                "empty_password_probe",
                StepResult(
                    probe.outcome,
                    f"empty password {verdict}",
                    probe.transcript,
                    channel=probe.channel,
                ),
                None,
            )
        )
        if not empty:
            return False
        async with self.e.store() as st:
            await st.flag_empty_password(self.ctx, on_device=True, steps=steps, candidate=candidate)
        return True

    async def verify_only(self) -> None:
        """A verify job (or a dry run): the current version, then the negative check."""
        version = self.ctx.account.secret_version
        current = await self.secret(version)
        if current == "":
            async with self.e.store() as st:
                await st.flag_empty_password(self.ctx)
            return
        steps: list[Step] = []
        if self.job.reason != VERIFY:  # a dry run: also connect the way a change would
            login = await self.login(after_change=False)
            dctx = self.dctx()
            try:
                session = await self.driver.connect(self.target, login, dctx)
                await session.close()
                steps.append(("dry_run_connect", StepResult(Outcome.OK, "connected"), None))
            except DriverError as exc:
                steps.append(("dry_run_connect", exc.result, None))
        pos = await self.verify(version)
        steps.append(("verify", pos, version))
        verdict = None
        if pos.ok:
            neg = await self.negative_check([current])
            verdict = self.negative_verdict(neg)
            steps.append(("verify_negative", self.negative_step(neg, verdict), None))
            sync = {VERIFIED: IN_SYNC, UNTRUSTWORTHY: VERIFY_UNTRUSTWORTHY}.get(verdict, UNVERIFIED)
        elif pos.outcome == Outcome.AUTH_FAILED:
            if await self.empty_on_device(steps):
                return
            sync = OUT_OF_SYNC
        elif pos.outcome == Outcome.REFUSED:
            await self.fail(pos.detail, steps[-1])
            return
        elif pos.outcome == Outcome.HOST_KEY_MISMATCH:
            who = f"{self.ctx.account.username}@{self.ctx.target.name}"  # recorded in verify()
            await self.fail(
                pos.detail,
                steps[-1],
                alert=("rotation.host_key_mismatch", f"Verify of {who}: {pos.detail}"),
            )
            return
        else:
            sync = UNREACHABLE
        dry = self.job.dry_run or self.job.reason != VERIFY
        detail = "dry run: nothing changed" if dry else None
        async with self.e.store() as st:
            await st.verify_finished(self.ctx, sync, verdict, steps=steps, detail=detail)
            if sync == OUT_OF_SYNC:
                await st.enqueue_auto_reconcile(self.ctx)
