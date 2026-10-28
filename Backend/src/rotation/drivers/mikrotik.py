"""MikroTik RouterOS over API-SSL with a pinned certificate (ROTATION.md §2, §15).

- Change (self): ``/password`` over API-SSL (old, new and confirm as API attributes).
- Reconcile: ``/user/set`` with the account's ``.id`` over API-SSL, as the reconcile
  account.
- Persist: not needed (RouterOS stores user changes at once).
- Verify: a fresh API-SSL login. Only when API-SSL is not enabled on the device does
  verify fall back to one SSH login (pinned host key); a change never does.
- Empty-password probe: one API-SSL login with an empty password. RouterOS accepts an
  empty-password account's empty password over the API (and only that one there), so an
  accepted probe proves the device password is empty. Over SSH such an account accepts
  ANY password, so the probe never runs over SSH.

Both identities must be pinned: the SSH host key and the API-SSL certificate. Before
any credential is sent the driver completes a TLS handshake that only the pinned
certificate can pass, then compares the SSH host key the device presents (read without
authenticating). A certificate mismatch stops before any SSH connection.
A mismatch on either blocks; it never falls back to the other channel. A password never
goes on an SSH command line or through the interactive console. The cleartext API
(8728) and Telnet are never used.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import asyncssh

from src.core.enums import Platform, Protocol
from src.rotation.drivers import ssh_login as ssh
from src.rotation.drivers.base import (
    AccountRef,
    Capability,
    Credential,
    DriverContext,
    DriverError,
    Identity,
    Outcome,
    StepResult,
    TargetRef,
)
from src.rotation.policy import PasswordPolicy, platform_default
from src.transport import routeros_api as api

API_SSL_DEFAULT_PORT = 8729
API_SSL = "api-ssl"
SSH = "ssh"
API_SSL_NOT_ENABLED = "API-SSL not enabled on device"
LEARN_IDENTITY = "learn the device identity first"
CLEARTEXT_API = "non-rotatable (cleartext API)"

# RouterOS user names: printable, no spaces or control characters.
_USERNAME = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$")
_PASSWORD_ATTRS = ("old-password", "new-password", "confirm-new-password", "password")


@dataclass
class MikroTikSession:
    login: Credential
    conn: api.ApiConnection

    async def close(self) -> None:
        await self.conn.close()


def _check_secret(value: str) -> None:
    if not value or any(c in value for c in "\r\n\x00"):
        raise ValueError("passwords must be non-empty single lines")


def identity_refusal(target: TargetRef) -> StepResult | None:
    """Why nothing may be sent to this target at all (checked before any connection)."""
    if not target.api_tls:
        return StepResult(
            Outcome.REFUSED, f"{target.name} is {CLEARTEXT_API}. Nothing was sent.", channel=None
        )
    if not (target.pinned_host_key and target.pinned_tls_pem and target.pinned_tls_fingerprint):
        missing = [
            name
            for name, value in (
                ("SSH host key", target.pinned_host_key),
                ("API-SSL certificate", target.pinned_tls_fingerprint),
            )
            if not value
        ]
        return StepResult(
            Outcome.REFUSED,
            f"{target.name}: {LEARN_IDENTITY} (pin the {' and the '.join(missing)} in "
            "Targets → Host key). Nothing was sent.",
        )
    return None


class MikroTikDriver:
    platform = Platform.MIKROTIK_ROUTEROS
    protocols = frozenset({Protocol.SSH})
    identities = frozenset({Identity.SSH, Identity.TLS})
    capabilities = frozenset(
        {
            Capability.CHANGE_SELF,
            Capability.CHANGE_VIA_RECONCILE,
            Capability.VERIFY,
            Capability.EMPTY_PROBE,
        }
    )
    default_policy: PasswordPolicy = platform_default(Platform.MIKROTIK_ROUTEROS)

    # ── identity and channel ──

    @staticmethod
    async def _ssh_identity(target: TargetRef, ctx: DriverContext) -> StepResult | None:
        """Compare the SSH host key the device presents with the pin (no credential is
        sent). A different key blocks; an unreadable one is noted and does not block,
        because the change never uses SSH."""
        pinned = asyncssh.import_public_key(target.pinned_host_key).get_fingerprint("sha256")
        presented = await ssh.presented_fingerprint(
            target.address, target.port, ctx.connect_timeout
        )
        if presented is None:
            ctx.transcript.write(f"[ssh host key of {target.name} unreadable; not used]\n")
            return None
        if presented != pinned:
            return StepResult(
                Outcome.HOST_KEY_MISMATCH,
                f"HOST KEY MISMATCH for {target.name}: SSH presented {presented}, not the "
                "pinned key. Nothing was sent.",
                presented_fingerprint=presented,
                identity=Identity.SSH,
                channel=SSH,
            )
        return None

    async def _open(self, target: TargetRef, ctx: DriverContext) -> api.ApiConnection | StepResult:
        """A TLS connection that only the pinned certificate can complete, then the SSH
        host-key comparison. A StepResult says why not; no API word was sent then. The
        certificate is checked first, so a certificate mismatch never touches SSH."""
        refused = identity_refusal(target)
        if refused is not None:
            return refused
        port = target.api_port or API_SSL_DEFAULT_PORT
        try:
            conn = await api.open_api_ssl(
                target.address,
                port,
                pinned_pem=target.pinned_tls_pem,
                pinned_fingerprint=target.pinned_tls_fingerprint,
                timeout=ctx.connect_timeout,
            )
        except api.CertificateMismatch as exc:
            if exc.presented is not None and exc.presented == api.normalise_fingerprint(
                target.pinned_tls_fingerprint
            ):
                # The pinned certificate itself no longer verifies (e.g. it expired).
                return StepResult(
                    Outcome.REFUSED,
                    f"The pinned API-SSL certificate of {target.name} failed verification "
                    f"({exc.verify_message}). Nothing was sent.",
                    channel=API_SSL,
                )
            return StepResult(
                Outcome.HOST_KEY_MISMATCH,
                f"CERTIFICATE MISMATCH for {target.name}: API-SSL presented "
                f"{exc.presented or 'an unreadable certificate'}, not the pinned one. "
                "Nothing was sent.",
                presented_fingerprint=exc.presented,
                identity=Identity.TLS,
                channel=API_SSL,
            )
        except api.Unavailable as exc:
            ctx.transcript.write(f"[{exc}]\n")
            if exc.timed_out:
                return StepResult(
                    Outcome.UNREACHABLE, f"API-SSL on {target.name} did not answer", channel=None
                )
            return StepResult(
                Outcome.CHANNEL_UNAVAILABLE,
                API_SSL_NOT_ENABLED,
                ctx.transcript.take(),
                channel=API_SSL,
            )
        ctx.transcript.write(f"[api-ssl {target.name}:{port}, pinned certificate verified]\n")
        mismatch = await self._ssh_identity(target, ctx)
        if mismatch is not None:
            await conn.close()
            return mismatch
        return conn

    @staticmethod
    def _result(
        conn: api.ApiConnection | None,
        ctx: DriverContext,
        outcome: Outcome,
        detail: str,
        channel: str | None = API_SSL,
    ) -> StepResult:
        if conn is not None:
            ctx.transcript.write("\n".join(conn.log) + "\n")
            conn.log.clear()
        return StepResult(
            outcome, ctx.transcript.redact(detail), ctx.transcript.take(), channel=channel
        )

    async def _api_login(
        self, target: TargetRef, username: str, secret: str, ctx: DriverContext
    ) -> tuple[api.ApiConnection | None, StepResult]:
        """One API-SSL login. (connection, OK) on success, else (None, why)."""
        opened = await self._open(target, ctx)
        if isinstance(opened, StepResult):
            return None, opened
        conn = opened
        try:
            accepted = await api.login(conn, username, secret)
        except api.ApiError as exc:
            await conn.close()
            return None, self._result(
                conn, ctx, Outcome.REJECTED_BY_DEVICE, f"login answered: {exc.message}"
            )
        except api.ConnectionLost as exc:
            await conn.close()
            return None, self._result(conn, ctx, Outcome.UNREACHABLE, f"login: {exc}")
        if not accepted:
            await conn.close()
            return None, self._result(
                conn, ctx, Outcome.AUTH_FAILED, f"{target.name} refused the login for {username}"
            )
        return conn, self._result(conn, ctx, Outcome.OK, f"logged in as {username} over API-SSL")

    # ── the driver interface ──

    async def connect(
        self, target: TargetRef, login: Credential, ctx: DriverContext
    ) -> MikroTikSession:
        ctx.transcript.add_secret(login.secret)
        conn, result = await self._api_login(target, login.username, login.secret, ctx)
        if conn is None:
            raise DriverError(result)
        return MikroTikSession(login, conn)

    async def change(
        self,
        session: MikroTikSession,
        account: AccountRef,
        current: str | None,
        new: str,
        ctx: DriverContext,
    ) -> StepResult:
        if current is None:
            return await self.reconcile(session, account, new, ctx)
        if session.login.username != account.username:
            return StepResult(Outcome.REJECTED_BY_DEVICE, "/password changes only its own user")
        _check_secret(current)
        _check_secret(new)
        ctx.transcript.add_secret(current)
        ctx.transcript.add_secret(new)
        conn = session.conn
        try:
            await conn.call(
                "/password",
                {"old-password": current, "new-password": new, "confirm-new-password": new},
                secret_attrs=_PASSWORD_ATTRS,
            )
        except api.ConnectionLost as exc:
            return self._result(conn, ctx, Outcome.AMBIGUOUS, str(exc))
        except api.ApiError as exc:
            outcome = (
                Outcome.AUTH_FAILED
                if "old password" in exc.message.lower()
                else Outcome.REJECTED_BY_DEVICE
            )
            return self._result(conn, ctx, outcome, f"the device refused: {exc.message}")
        return self._result(conn, ctx, Outcome.OK, "password changed (/password over API-SSL)")

    async def persist(self, session: MikroTikSession, ctx: DriverContext) -> StepResult:
        return StepResult(Outcome.OK, "not needed on RouterOS (user changes are stored at once)")

    async def reconcile(
        self, session: MikroTikSession, account: AccountRef, new: str, ctx: DriverContext
    ) -> StepResult:
        if not _USERNAME.match(account.username):
            return StepResult(Outcome.REJECTED_BY_DEVICE, "unsupported user name")
        _check_secret(new)
        ctx.transcript.add_secret(new)
        conn = session.conn
        try:
            rows = await conn.call("/user/print", queries=[f"?name={account.username}"])
        except api.ConnectionLost as exc:
            return self._result(conn, ctx, Outcome.UNREACHABLE, str(exc))
        except api.ApiError as exc:
            return self._result(conn, ctx, Outcome.REJECTED_BY_DEVICE, exc.message)
        ids = [r[".id"] for r in rows if r.get("name") == account.username and r.get(".id")]
        if len(ids) != 1:
            return self._result(
                conn, ctx, Outcome.REJECTED_BY_DEVICE, f"no single user {account.username}"
            )
        try:
            await conn.call(
                "/user/set", {".id": ids[0], "password": new}, secret_attrs=_PASSWORD_ATTRS
            )
        except api.ConnectionLost as exc:
            return self._result(conn, ctx, Outcome.AMBIGUOUS, str(exc))
        except api.ApiError as exc:
            detail = f"the device refused: {exc.message}"
            if "permission" in exc.message.lower():
                detail = "the reconcile account may not set user passwords (needs write, policy)"
            return self._result(conn, ctx, Outcome.REJECTED_BY_DEVICE, detail)
        return self._result(conn, ctx, Outcome.OK, "password set (/user/set over API-SSL)")

    async def verify(
        self, target: TargetRef, account: AccountRef, secret: str, ctx: DriverContext
    ) -> StepResult:
        """One fresh login: over API-SSL; over SSH only if API-SSL is not enabled."""
        ctx.transcript.add_secret(secret)
        conn, result = await self._api_login(target, account.username, secret, ctx)
        if conn is not None:
            await conn.close()
            return result
        if result.outcome != Outcome.CHANNEL_UNAVAILABLE:
            return result  # a mismatch, refusal or answer never falls back to SSH
        try:
            ssh_conn = await ssh.ssh_login(
                target, account.username, secret, timeout=ctx.connect_timeout
            )
        except DriverError as exc:
            r = exc.result
            return StepResult(
                r.outcome,
                f"{API_SSL_NOT_ENABLED}; over SSH: {r.detail}",
                result.transcript,
                presented_fingerprint=r.presented_fingerprint,
                identity=Identity.SSH,
                channel=SSH,
            )
        ssh_conn.close()
        return StepResult(
            Outcome.OK,
            f"{API_SSL_NOT_ENABLED}; logged in as {account.username} over SSH",
            result.transcript,
            channel=SSH,
        )

    async def probe_empty_password(
        self, target: TargetRef, account: AccountRef, ctx: DriverContext
    ) -> StepResult:
        """One API-SSL login with an empty password. OK means the device password IS
        empty; AUTH_FAILED means it is not; anything else proves nothing. Never SSH."""
        conn, result = await self._api_login(target, account.username, "", ctx)
        if conn is not None:
            await conn.close()
            return StepResult(
                Outcome.OK,
                f"{account.username} accepted an EMPTY password over API-SSL",
                result.transcript,
                channel=API_SSL,
            )
        return result
