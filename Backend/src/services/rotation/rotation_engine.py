"""The rotation state machine (ROTATION.md section 5).

pending → (waiting_release) → running → candidate_stored → device_changed → persisted
→ succeeded | changed_unverified, or failed | needs_attention.

Each state is committed (RotationStore) before the next device step, so a crash at any
point resumes from the last committed state with the recovery rule for that state:

- running: nothing was stored or sent; start again.
- candidate_stored, change not yet sent: the device is untouched; send the change.
- candidate_stored, change sent (or the answer was ambiguous): verify C; if it works
  the device changed. Otherwise verify N: if N works the change never happened, so
  retry; if neither works, needs_attention.
- device_changed: persist (idempotent), then verify.
- persisted: verify C (then the single negative check) and promote; if C fails,
  verify N as above.

The final verify is a fresh login with C and then exactly ONE login with a fresh
wrong password, which must be refused (section 6). Every driver gets this from here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.contracts.dto.rotation.rotation_dto import (
    CANDIDATE_STORED,
    DEVICE_CHANGED,
    PERSISTED,
    RECONCILE,
    RUNNING,
    VERIFY,
    RotationContextDTO,
)
from src.core.enums import Protocol
from src.rotation.drivers.base import (
    AccountRef,
    Capability,
    Credential,
    DriverContext,
    PlatformDriver,
    TargetRef,
    Transcript,
)
from src.rotation.drivers.registry import DriverRegistry
from src.services.rotation.rotation_run import JobRun
from src.services.rotation.rotation_store import RotationStore

logger = structlog.get_logger(__name__)

TELNET_REFUSAL = "non-rotatable (Telnet)"


class SimulatedCrash(BaseException):  # noqa: N818 - tests only: a process dying mid-job
    """Raised by a test checkpoint to stop the engine as if the process died."""


Checkpoint = Callable[[str], Awaitable[None]]


async def _no_checkpoint(_: str) -> None:
    return None


def refusal(ctx: RotationContextDTO, driver: PlatformDriver | None, *, enabled: bool) -> str | None:
    """Why this job must not touch the device at all (checked before any connection)."""
    target, account, job = ctx.target, ctx.account, ctx.job
    if not enabled:
        return "Rotation is switched off on this WardX instance (WARDX_ROTATION_ENABLED)"
    if not target.rotation_allowed:
        return f"Rotation is not allowed on target {target.name}"
    if target.protocol == Protocol.TELNET:
        return f"{target.name} is {TELNET_REFUSAL}"
    if not target.is_active:
        return f"Target {target.name} is inactive"
    if driver is None:
        return f"No rotation driver for platform {target.platform}"
    if target.protocol not in getattr(driver, "protocols", {Protocol.SSH}):
        return f"The {target.platform} driver does not rotate over {target.protocol}"
    if account.secret_type != "password":
        return "Only passwords are rotated (SSH keys come later)"
    if target.protocol == Protocol.SSH and not target.ssh_host_key:
        return (
            f"{target.name} has no pinned SSH host key; pin it (Targets → Learn host key) "
            "before rotating. Nothing was sent."
        )
    via_reconcile = job.reason == RECONCILE or Capability.CHANGE_SELF not in driver.capabilities
    if job.reason == VERIFY:
        return None if account.secret_version else "No secret is stored for this account"
    if via_reconcile and job.reason != VERIFY:
        if Capability.CHANGE_VIA_RECONCILE not in driver.capabilities:
            return f"The {target.platform} driver cannot change through a reconcile account"
        if ctx.reconcile is None:
            return "This account has no reconcile account"
        if not ctx.reconcile.secret_version:
            return "The reconcile account has no stored secret"
    elif not account.secret_version:
        return "No secret is stored for this account"
    return None


class RotationEngine:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        store_factory: Callable[[AsyncSession], RotationStore],
        registry: DriverRegistry,
        *,
        enabled: bool,
        dry_run: bool = False,
        connect_timeout: float = 15.0,
        command_timeout: float = 20.0,
        checkpoint: Checkpoint | None = None,
    ) -> None:
        self._sessions = sessions
        self._store_factory = store_factory
        self.registry = registry
        self.enabled = enabled
        self.dry_run = dry_run
        self.connect_timeout = connect_timeout
        self.command_timeout = command_timeout
        self.checkpoint = checkpoint or _no_checkpoint

    @asynccontextmanager
    async def store(self):
        async with self._sessions() as session:
            yield self._store_factory(session)

    def driver_context(self, secrets: list[str]) -> DriverContext:
        return DriverContext(
            Transcript(secrets),
            connect_timeout=self.connect_timeout,
            command_timeout=self.command_timeout,
        )

    async def run(self, job_id: Any) -> None:
        """Drive one claimed job as far as it can go now."""
        async with self.store() as st:
            ctx = await st.context(job_id)
        if ctx is None:
            return
        driver = self.registry.get(ctx.target.platform)
        why = refusal(ctx, driver, enabled=self.enabled)
        if why is not None:
            async with self.store() as st:
                if self._device_may_hold_candidate(ctx):
                    # Never forget a password the device may already use: an admin decides.
                    await st.needs_attention(ctx, f"Stopped mid-rotation: {why}")
                else:
                    await st.fail(ctx, why, candidate=self._unpromoted(ctx))
            return
        await JobRun(self, ctx, driver).go()

    @staticmethod
    def _device_may_hold_candidate(ctx: RotationContextDTO) -> bool:
        job = ctx.job
        return job.status in (DEVICE_CHANGED, PERSISTED) or (
            job.status == CANDIDATE_STORED and job.change_sent_at is not None
        )

    @staticmethod
    def _unpromoted(ctx: RotationContextDTO) -> int | None:
        job = ctx.job
        if job.status in (RUNNING, CANDIDATE_STORED) and job.change_sent_at is None:
            return job.candidate_version
        return None

    @staticmethod
    def target_ref(ctx: RotationContextDTO) -> TargetRef:
        t = ctx.target
        return TargetRef(t.id, t.name, t.address, t.port, t.platform, t.protocol, t.ssh_host_key)

    @staticmethod
    def account_ref(ctx: RotationContextDTO) -> AccountRef:
        return AccountRef(ctx.account.id, ctx.account.username)

    @staticmethod
    def credential(username: str, secret: str) -> Credential:
        return Credential(username, secret)


__all__ = [
    "CANDIDATE_STORED",
    "DEVICE_CHANGED",
    "PERSISTED",
    "RotationEngine",
    "SimulatedCrash",
    "refusal",
]
