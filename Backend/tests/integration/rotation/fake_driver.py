"""A simulated device and driver for the rotation state machine tests.

The device keeps one password per user. Faults are queued per method and consumed in
order, so a test can make exactly one step fail in exactly one way.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from src.rotation.drivers.base import (
    Capability,
    Credential,
    DriverContext,
    DriverError,
    Outcome,
    StepResult,
)
from src.rotation.policy import platform_default
from src.services.rotation.rotation_engine import SimulatedCrash

FAKE_PLATFORM = "generic"


@dataclass
class FakeSession:
    login: Credential
    closed: bool = False

    async def close(self) -> None:
        self.closed = True


@dataclass
class FakeDevice:
    passwords: dict[str, str] = field(default_factory=dict)
    # A device that accepts any password (RouterOS with an empty password, a broken PAM).
    accept_any: bool = False


class FakeDriver:
    platform = FAKE_PLATFORM
    protocols = frozenset({"ssh"})
    default_policy = platform_default("linux")

    def __init__(self, device: FakeDevice, *, persist: bool = True, self_change: bool = True):
        self.device = device
        caps = {Capability.CHANGE_VIA_RECONCILE, Capability.VERIFY}
        if persist:
            caps.add(Capability.PERSIST)
        if self_change:
            caps.add(Capability.CHANGE_SELF)
        self.capabilities = frozenset(caps)
        self.faults: dict[str, list[str]] = defaultdict(list)
        self.calls: list[tuple[str, str]] = []
        # Every secret any verify was called with (to count wrong-password attempts).
        self.verified: list[str] = []

    def fail(self, method: str, *faults: str) -> None:
        self.faults[method].extend(faults)

    def _fault(self, method: str) -> str | None:
        queue = self.faults.get(method)
        return queue.pop(0) if queue else None

    def _accepts(self, user: str, secret: str) -> bool:
        return self.device.accept_any or self.device.passwords.get(user) == secret

    def count(self, method: str) -> int:
        return sum(1 for m, _ in self.calls if m == method)

    async def connect(self, target, login: Credential, ctx: DriverContext) -> FakeSession:
        self.calls.append(("connect", login.username))
        fault = self._fault("connect")
        if fault == "unreachable":
            raise DriverError(StepResult(Outcome.UNREACHABLE, "no route to host"))
        if fault == "host_key":
            raise DriverError(StepResult(Outcome.HOST_KEY_MISMATCH, "host key mismatch"))
        if not self._accepts(login.username, login.secret):
            raise DriverError(StepResult(Outcome.AUTH_FAILED, "login refused"))
        return FakeSession(login)

    def _apply(self, user: str, new: str, fault: str | None) -> StepResult:
        if fault == "unreachable":
            return StepResult(Outcome.UNREACHABLE, "could not start the command")
        if fault == "rejected":
            return StepResult(Outcome.REJECTED_BY_DEVICE, "complexity rule")
        if fault == "ambiguous_lost":
            return StepResult(Outcome.AMBIGUOUS, "connection dropped")
        self.device.passwords[user] = new
        if fault == "ambiguous_applied":
            return StepResult(Outcome.AMBIGUOUS, "connection dropped")
        if fault == "crash_after_apply":
            raise SimulatedCrash("process died after the device accepted the change")
        return StepResult(Outcome.OK, "changed", ctx_transcript(new))

    async def change(self, session, account, current, new, ctx) -> StepResult:
        self.calls.append(("change", account.username))
        fault = self._fault("change")
        if fault is None and current is not None and not self._accepts(account.username, current):
            return StepResult(Outcome.AUTH_FAILED, "current password refused")
        return self._apply(account.username, new, fault)

    async def reconcile(self, session, account, new, ctx) -> StepResult:
        self.calls.append(("reconcile", account.username))
        return self._apply(account.username, new, self._fault("reconcile"))

    async def persist(self, session, ctx) -> StepResult:
        self.calls.append(("persist", session.login.username))
        if self._fault("persist") == "fail":
            return StepResult(Outcome.REJECTED_BY_DEVICE, "save failed")
        return StepResult(Outcome.OK, "saved")

    async def verify(self, target, account, secret, ctx) -> StepResult:
        self.calls.append(("verify", account.username))
        self.verified.append(secret)
        fault = self._fault("verify")
        if fault == "unreachable":
            return StepResult(Outcome.UNREACHABLE, "timed out")
        if self._accepts(account.username, secret):
            return StepResult(Outcome.OK, "logged in")
        return StepResult(Outcome.AUTH_FAILED, "login refused")


def ctx_transcript(new: str) -> str:
    """What a careless device would echo; the engine must never store it unredacted."""
    return f"set password {new}\n".replace(new, "****")
