"""One run of one claimed job through the state machine (see rotation_engine.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from src.contracts.dto.rotation.rotation_dto import (
    CANDIDATE_STORED,
    DEVICE_CHANGED,
    INCONCLUSIVE,
    OUT_OF_SYNC,
    PERSISTED,
    RECONCILE,
    RUNNING,
    UNTRUSTWORTHY,
    VERIFIED,
    VERIFY,
    RotationContextDTO,
)
from src.rotation import policy as policies
from src.rotation.drivers.base import (
    Capability,
    Credential,
    DriverError,
    Outcome,
    PlatformDriver,
    StepResult,
)
from src.rotation.passwords import generate, wrong_password
from src.services.rotation.rotation_verify import VerifyMixin

if TYPE_CHECKING:
    from src.services.rotation.rotation_engine import RotationEngine

logger = structlog.get_logger(__name__)

# Retries back off 1, 5 and 15 minutes; a job is claimed at most this many times.
BACKOFF_SECONDS = (60, 300, 900)
MAX_ATTEMPTS = 3

Step = tuple[str, StepResult, int | None]


class JobRun(VerifyMixin):
    def __init__(self, engine: RotationEngine, ctx: RotationContextDTO, driver: PlatformDriver):
        self.e = engine
        self.ctx = ctx
        self.driver = driver
        self.job = ctx.job
        # N: the version the job started from (or, before step 2, the current one).
        self.n = (
            ctx.job.from_version if ctx.job.from_version is not None else ctx.account.secret_version
        )
        self.c = ctx.job.candidate_version
        self.via_reconcile = (
            ctx.job.reason == RECONCILE or Capability.CHANGE_SELF not in driver.capabilities
        )
        self.target = engine.target_ref(ctx)
        self.account = engine.account_ref(ctx)
        self._secrets: dict[int, str] = {}

    # ── helpers ──

    async def secret(self, version: int) -> str:
        if version not in self._secrets:
            async with self.e.store() as st:
                self._secrets[version] = await st.read_secret(self.ctx.account.id, version)
        return self._secrets[version]

    async def login(self, *, after_change: bool) -> Credential:
        """Who connects for a device step: the account itself, or its reconcile account."""
        if self.via_reconcile:
            rec = self.ctx.reconcile
            async with self.e.store() as st:
                value = await st.read_secret(rec.id, rec.secret_version)
            return Credential(rec.username, value)
        version = self.c if after_change else self.n
        return Credential(self.ctx.account.username, await self.secret(version))

    def dctx(self):
        return self.e.driver_context(list(self._secrets.values()))

    async def checkpoint(self, name: str) -> None:
        await self.e.checkpoint(name)

    async def retry(
        self,
        status: str,
        detail: str,
        step: Step | None,
        *,
        on_exhausted,
        **changes,
    ) -> None:
        """Back off and try again later, or give up the way the state demands."""
        if self.job.attempts < MAX_ATTEMPTS:
            delay = BACKOFF_SECONDS[min(self.job.attempts, len(BACKOFF_SECONDS)) - 1]
            async with self.e.store() as st:
                await st.reschedule(self.ctx, status, delay, detail, step=step, **changes)
            return
        await on_exhausted(f"{detail} (gave up after {self.job.attempts} attempts)", step)

    async def fail(self, detail: str, step: Step | None = None, **kwargs) -> None:
        async with self.e.store() as st:
            await st.fail(self.ctx, detail, step=step, **kwargs)

    async def fail_abandon(self, detail: str, step: Step | None = None) -> None:
        await self.fail(detail, step, candidate=self.c)

    async def attention(self, detail: str, step: Step | None = None) -> None:
        async with self.e.store() as st:
            await st.needs_attention(self.ctx, detail, step=step)

    async def advance(self, status: str, step: Step | None = None, **changes) -> str:
        async with self.e.store() as st:
            await st.advance(self.job.id, status, step=step, **changes)
        await self.checkpoint(status)
        return status

    async def verify(self, version: int | None, secret: str | None = None) -> StepResult:
        """A positive login with one version (or a given secret)."""
        value = secret if secret is not None else await self.secret(version)
        dctx = self.e.driver_context([value, *self._secrets.values()])
        result = await self.driver.verify(self.target, self.account, value, dctx)
        if result.outcome == Outcome.HOST_KEY_MISMATCH:
            await self.record_mismatch(result, "verify")
        return result

    async def record_mismatch(self, result: StepResult, source: str) -> None:
        """Another host key or certificate: recorded on the target, which blocks every
        later rotation and verify there until an administrator accepts one."""
        async with self.e.store() as st:
            await st.record_host_key_mismatch(
                self.ctx, result.presented_fingerprint, source=source, identity=result.identity
            )

    async def negative_check(self, known: list[str]) -> StepResult:
        """Exactly one login with a fresh wrong password; it must be refused. Never retried."""
        pol = self.policy()
        wrong = wrong_password(pol)
        while wrong in known:  # pragma: no cover - astronomically unlikely
            wrong = wrong_password(pol)
        dctx = self.e.driver_context([wrong, *known])
        result = await self.driver.verify(self.target, self.account, wrong, dctx)
        del wrong
        return result

    @staticmethod
    def negative_verdict(result: StepResult) -> str:
        if result.outcome == Outcome.AUTH_FAILED:
            return VERIFIED
        if result.outcome == Outcome.OK:
            return UNTRUSTWORTHY
        return INCONCLUSIVE

    def policy(self) -> policies.PasswordPolicy:
        t = self.ctx.target
        return policies.resolve(t.platform, t.policy_overrides, self.ctx.account.password_length)

    # ── the machine ──

    async def go(self) -> None:
        global_dry_run = self.e.dry_run and self.job.status == RUNNING
        if self.job.reason == VERIFY or self.job.dry_run or global_dry_run:
            await self.verify_only()
            return
        status = self.job.status
        fresh = False
        if status == RUNNING:
            async with self.e.store() as st:
                if await st.wait_for_release(self.ctx) is not None:
                    return
            status = await self.store_candidate()
            fresh = True
        if status == CANDIDATE_STORED:
            if self.job.change_sent_at is not None and not fresh:
                status = await self.resolve_uncertain()
            if status == CANDIDATE_STORED:
                status = await self.change()
        if status == DEVICE_CHANGED:
            status = await self.persist()
        if status == PERSISTED:
            await self.final_verify()

    async def store_candidate(self) -> str | None:
        """Steps 1 and 2: generate C per policy and store it before the device is touched."""
        try:
            candidate = generate(self.policy(), self.ctx.account.username)
        except (policies.PolicyError, ValueError) as exc:
            await self.fail(f"Password policy: {exc}")
            return None
        try:
            async with self.e.store() as st:
                self.n, self.c = await st.store_candidate(
                    self.ctx, candidate, str(self.driver.platform)
                )
        except Exception as exc:  # noqa: BLE001 - any vault failure: device never touched
            logger.warning("rotation_vault_write_failed", job_id=str(self.job.id))
            await self.fail(f"Storing the new password in the vault failed: {type(exc).__name__}")
            return None
        self._secrets[self.c] = candidate
        await self.checkpoint(CANDIDATE_STORED)
        return CANDIDATE_STORED

    async def on_connect_failure(self, result: StepResult, step_name: str) -> None:
        step = (step_name, result, self.n)
        who = f"{self.ctx.account.username}@{self.ctx.target.name}"
        if result.outcome == Outcome.HOST_KEY_MISMATCH:
            await self.record_mismatch(result, "rotation")
            await self.fail(
                result.detail,
                step,
                candidate=self.c,
                alert=("rotation.host_key_mismatch", f"Rotation of {who}: {result.detail}"),
            )
        elif result.outcome == Outcome.CHANNEL_UNAVAILABLE:
            # The device offers no secure change channel: an administrator must enable it.
            # Nothing was sent, and there is no fallback to a weaker channel.
            await self.attention(result.detail, step)
        elif result.outcome == Outcome.REFUSED:
            await self.fail_abandon(result.detail, step)
        elif result.outcome == Outcome.AUTH_FAILED and not self.via_reconcile:
            if await self.empty_on_device([step], candidate=self.c):
                return
            await self.fail(
                f"{who} rejected its current vaulted password (N)",
                step,
                candidate=self.c,
                sync_status=OUT_OF_SYNC,
                alert=("rotation.out_of_sync", f"{who} rejected its vaulted password"),
            )
            async with self.e.store() as st:
                await st.enqueue_auto_reconcile(self.ctx)
        elif result.outcome == Outcome.AUTH_FAILED:
            await self.fail(
                "The reconcile account's password was rejected",
                step,
                candidate=self.c,
                alert=("rotation.reconcile_rejected", f"Reconcile account for {who} rejected"),
            )
        else:
            await self.retry(CANDIDATE_STORED, result.detail, step, on_exhausted=self.fail_abandon)

    async def change(self) -> str | None:
        """Steps 3 and 4: connect with N (or the reconcile account) and set C."""
        login = await self.login(after_change=False)
        dctx = self.dctx()
        try:
            session = await self.driver.connect(self.target, login, dctx)
        except DriverError as exc:
            await self.on_connect_failure(exc.result, "connect")
            return None
        try:
            if self.via_reconcile:
                async with self.e.store() as st:
                    await st.audit_reconcile_account_use(self.ctx)
            async with self.e.store() as st:
                if not await st.mark_change_sent(self.ctx, self.c):
                    return None  # a holder appeared (emergency): wait, device untouched
            await self.checkpoint("change_sent")
            new = await self.secret(self.c)
            if self.via_reconcile:
                result = await self.driver.reconcile(session, self.account, new, dctx)
            else:
                current = await self.secret(self.n)
                if current == "":
                    async with self.e.store() as st:
                        await st.flag_empty_password(self.ctx)
                    return None
                result = await self.driver.change(session, self.account, current, new, dctx)
        finally:
            await session.close()
        await self.checkpoint("device_answered")
        step = ("reconcile" if self.via_reconcile else "change", result, self.c)
        if result.ok:
            return await self.advance(DEVICE_CHANGED, step)
        if result.outcome == Outcome.AMBIGUOUS:
            async with self.e.store() as st:
                await st.step(self.job.id, *step)
            return await self.resolve_uncertain()
        if result.outcome == Outcome.UNREACHABLE:
            await self.retry(CANDIDATE_STORED, result.detail, step, on_exhausted=self.fail_abandon)
            return None
        await self.fail_abandon(f"The device refused the change: {result.detail}", step)
        return None

    async def resolve_uncertain(self) -> str | None:
        """The device may or may not hold C: verify C, then N."""
        c_res = await self.verify(self.c)
        c_step = ("recover_verify_candidate", c_res, self.c)
        if c_res.ok:
            return await self.advance(DEVICE_CHANGED, c_step)
        if c_res.outcome != Outcome.AUTH_FAILED:
            await self.retry(CANDIDATE_STORED, c_res.detail, c_step, on_exhausted=self.attention)
            return None
        async with self.e.store() as st:
            await st.step(self.job.id, *c_step)
        n_res = await self.verify(self.n)
        n_step = ("recover_verify_current", n_res, self.n)
        if n_res.ok:
            # The change never happened: send it again later (same candidate).
            await self.retry(
                CANDIDATE_STORED,
                "The device still uses the current password; the change will be retried",
                n_step,
                on_exhausted=self.fail_abandon,
                change_sent_at=None,
            )
            return None
        if n_res.outcome == Outcome.AUTH_FAILED:
            await self.attention("Neither the new nor the current password works", n_step)
            return None
        await self.retry(CANDIDATE_STORED, n_res.detail, n_step, on_exhausted=self.attention)
        return None

    async def persist(self) -> str | None:
        """Step 5: save on the device (network platforms); retry once, else roll back."""
        if Capability.PERSIST not in self.driver.capabilities:
            return await self.advance(
                PERSISTED, ("persist", StepResult(Outcome.OK, "not needed"), self.c)
            )
        login = await self.login(after_change=True)
        last: StepResult | None = None
        for _ in range(2):
            dctx = self.dctx()
            try:
                session = await self.driver.connect(self.target, login, dctx)
            except DriverError as exc:
                await self.retry(
                    DEVICE_CHANGED,
                    exc.result.detail,
                    ("persist", exc.result, self.c),
                    on_exhausted=self.attention,
                )
                return None
            try:
                last = await self.driver.persist(session, dctx)
            finally:
                await session.close()
            if last.ok:
                return await self.advance(PERSISTED, ("persist", last, self.c))
            async with self.e.store() as st:
                await st.step(self.job.id, "persist", last, self.c)
        return await self.rollback(login, last)

    async def rollback(self, login: Credential, cause: StepResult | None) -> None:
        """The save failed twice: put N back on the device, then prove N works."""
        dctx = self.dctx()
        n = await self.secret(self.n)
        try:
            session = await self.driver.connect(self.target, login, dctx)
        except DriverError as exc:
            await self.attention(
                "Save failed and the rollback could not connect", ("rollback", exc.result, self.n)
            )
            return None
        try:
            if self.via_reconcile:
                back = await self.driver.reconcile(session, self.account, n, dctx)
            else:
                back = await self.driver.change(
                    session, self.account, await self.secret(self.c), n, dctx
                )
        finally:
            await session.close()
        async with self.e.store() as st:
            await st.step(self.job.id, "rollback", back, self.n)
        check = await self.verify(self.n)
        if back.ok and check.ok:
            detail = f"Saving on the device failed ({cause.detail if cause else ''}); rolled back"
            await self.fail_abandon(detail, ("rollback_verify", check, self.n))
            return None
        await self.attention(
            "Save failed and the rollback to N did not verify", ("rollback_verify", check, self.n)
        )
        return None

    async def final_verify(self) -> None:
        """Step 6 and 7: a fresh login with C, the single negative check, then promote."""
        c_res = await self.verify(self.c)
        c_step = ("verify", c_res, self.c)
        if c_res.ok:
            known = [await self.secret(self.c)] + ([await self.secret(self.n)] if self.n else [])
            neg = await self.negative_check(known)
            verdict = self.negative_verdict(neg)
            n_step = ("verify_negative", self.negative_step(neg, verdict), None)
            async with self.e.store() as st:
                await st.promote(self.ctx, self.c, verdict, steps=[c_step, n_step])
            return
        if c_res.outcome != Outcome.AUTH_FAILED:
            await self.retry(PERSISTED, c_res.detail, c_step, on_exhausted=self.attention)
            return
        async with self.e.store() as st:
            await st.step(self.job.id, *c_step)
        n_res = await self.verify(self.n) if self.n else StepResult(Outcome.AUTH_FAILED)
        n_step = ("verify_current", n_res, self.n)
        if n_res.ok:
            await self.retry(
                CANDIDATE_STORED,
                "The device did not keep the new password; the change will be retried",
                n_step,
                on_exhausted=self.fail_abandon,
                change_sent_at=None,
            )
        elif n_res.outcome == Outcome.AUTH_FAILED:
            await self.attention("Neither the new nor the current password works", n_step)
        else:
            await self.retry(PERSISTED, n_res.detail, n_step, on_exhausted=self.attention)
