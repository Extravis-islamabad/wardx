"""The platform plugin interface (ROTATION.md section 2).

A driver only talks to the device: no policy, scheduling or vault logic. Every
secret it handles is in ``DriverContext.secrets`` so transcripts are redacted, and
no secret ever goes into a command line (argv): passwords travel through
interactive prompts or stdin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from src.rotation.policy import PasswordPolicy

REDACTED = "****"
_TRANSCRIPT_LIMIT = 20_000


class Capability(StrEnum):
    CHANGE_SELF = "change_self"
    CHANGE_VIA_RECONCILE = "change_via_reconcile"
    VERIFY = "verify"
    PERSIST = "persist"
    SSH_KEY = "ssh_key"
    # The driver can tell, without side effects, whether the account's device password
    # is empty (MikroTik: an empty-password login over the API).
    EMPTY_PROBE = "empty_probe"


class Identity(StrEnum):
    """A device identity WardX pins: the SSH host key, or a TLS certificate."""

    SSH = "ssh"
    TLS = "tls"


class Outcome(StrEnum):
    OK = "ok"
    AUTH_FAILED = "auth_failed"
    REJECTED_BY_DEVICE = "rejected_by_device"
    UNREACHABLE = "unreachable"
    HOST_KEY_MISMATCH = "host_key_mismatch"
    # The command was sent, but the connection dropped before a definite answer.
    AMBIGUOUS = "ambiguous"
    BLOCKED_BY_DEPENDENTS = "blocked_by_dependents"
    # The secure channel the driver must use is not offered (MikroTik: API-SSL off).
    # Nothing was sent; an administrator must enable it (needs attention).
    CHANNEL_UNAVAILABLE = "channel_unavailable"
    # WardX refused before sending anything (e.g. an identity is not pinned).
    REFUSED = "refused"


@dataclass(frozen=True)
class StepResult:
    outcome: Outcome
    detail: str = ""
    transcript: str = ""
    # HOST_KEY_MISMATCH only: the fingerprint the device presented instead of the pin
    # (SHA256:...), when it could be read. Recorded on the target; never trusted.
    presented_fingerprint: str | None = None
    # HOST_KEY_MISMATCH only: which pinned identity did not match.
    identity: Identity = Identity.SSH
    # The device channel used (api-ssl, ssh), recorded on the job step.
    channel: str | None = None

    @property
    def ok(self) -> bool:
        return self.outcome == Outcome.OK


class DriverError(Exception):
    """Raised by ``connect`` when no session could be opened; carries the step result."""

    def __init__(self, result: StepResult) -> None:
        super().__init__(result.detail)
        self.result = result


@dataclass(frozen=True)
class TargetRef:
    id: Any
    name: str
    address: str
    port: int
    platform: str
    protocol: str
    # Pinned SSH host public key (OpenSSH format); None = not pinned (rotation refuses).
    pinned_host_key: str | None
    # Drivers that change over a TLS API (MikroTik API-SSL): the pinned certificate (PEM)
    # and its SHA-256 fingerprint, the API port (None = the driver's default) and
    # whether the device's API is TLS at all (False = cleartext only, never used).
    pinned_tls_pem: str | None = field(default=None, repr=False)
    pinned_tls_fingerprint: str | None = None
    api_port: int | None = None
    api_tls: bool = True


@dataclass(frozen=True)
class AccountRef:
    id: Any
    username: str


@dataclass(frozen=True)
class Credential:
    username: str
    secret: str = field(repr=False)


class Transcript:
    """Collects a step's device conversation, replacing every known secret with ****."""

    def __init__(self, secrets: list[str]) -> None:
        self._secrets = sorted({s for s in secrets if s}, key=len, reverse=True)
        self._parts: list[str] = []

    def add_secret(self, secret: str) -> None:
        if secret and secret not in self._secrets:
            self._secrets = sorted([*self._secrets, secret], key=len, reverse=True)

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return text

    def write(self, text: str) -> None:
        self._parts.append(self.redact(text))

    def take(self) -> str:
        """The redacted text so far (and start a new fragment)."""
        text = "".join(self._parts)[-_TRANSCRIPT_LIMIT:]
        self._parts = []
        return self.redact(text)


@dataclass
class DriverContext:
    transcript: Transcript
    connect_timeout: float = 15.0
    command_timeout: float = 20.0


@runtime_checkable
class DriverSession(Protocol):
    login: Credential

    async def close(self) -> None: ...


class PlatformDriver(Protocol):
    platform: str
    capabilities: frozenset[Capability]
    default_policy: PasswordPolicy

    async def connect(
        self, target: TargetRef, login: Credential, ctx: DriverContext
    ) -> DriverSession: ...

    async def change(
        self,
        session: DriverSession,
        account: AccountRef,
        current: str | None,
        new: str,
        ctx: DriverContext,
    ) -> StepResult: ...

    async def persist(self, session: DriverSession, ctx: DriverContext) -> StepResult: ...

    async def verify(
        self, target: TargetRef, account: AccountRef, secret: str, ctx: DriverContext
    ) -> StepResult: ...

    async def reconcile(
        self, session: DriverSession, account: AccountRef, new: str, ctx: DriverContext
    ) -> StepResult: ...
