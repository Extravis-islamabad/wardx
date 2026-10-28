"""Linux / Unix over SSH (ROTATION.md section 2).

- Change (self): ``passwd`` run directly in a pseudo-terminal; the current and new
  passwords are typed at its prompts, never put on a command line.
- Reconcile: ``sudo -n /usr/sbin/chpasswd`` as the reconcile account, with
  ``user:password`` written to its stdin.
- Persist: not needed (the change is durable).
- Verify: a fresh SSH login as the account (pinned host key, one attempt).
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

import asyncssh

from src.core.enums import Platform, Protocol
from src.rotation.cli import Cli, CliError
from src.rotation.drivers.base import (
    AccountRef,
    Capability,
    Credential,
    DriverContext,
    DriverError,
    Outcome,
    StepResult,
    TargetRef,
)
from src.rotation.drivers.ssh_login import ssh_login
from src.rotation.policy import PasswordPolicy, platform_default

# POSIX-ish user names: never a colon or newline (they would break chpasswd's input).
_USERNAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,31}\$?$")
PASSWD_COMMAND = "env LC_ALL=C passwd"
CHPASSWD_COMMAND = "sudo -n /usr/sbin/chpasswd"

_CURRENT = r"(current|old)[^\n]*password[^\n]*:\s*$"
_NEW = r"^\s*new [^\n]*password[^\n]*:\s*$"
_RETYPE = r"(retype|re-enter|again)[^\n]*password[^\n]*:\s*$"
_UPDATED = r"(updated successfully|all authentication tokens updated)"
_FAILED = r"(manipulation error|password unchanged|do not match|authentication failure)"


@dataclass
class LinuxSession:
    login: Credential
    conn: asyncssh.SSHClientConnection

    async def close(self) -> None:
        self.conn.close()
        try:
            await asyncio.wait_for(self.conn.wait_closed(), 5)
        except (TimeoutError, OSError, asyncssh.Error):
            pass


def _check_secret(value: str) -> None:
    if not value or "\n" in value or "\r" in value:
        raise ValueError("passwords must be non-empty single lines")


class LinuxDriver:
    platform = Platform.LINUX
    protocols = frozenset({Protocol.SSH})
    capabilities = frozenset(
        {Capability.CHANGE_SELF, Capability.CHANGE_VIA_RECONCILE, Capability.VERIFY}
    )
    default_policy: PasswordPolicy = platform_default(Platform.LINUX)

    async def connect(
        self, target: TargetRef, login: Credential, ctx: DriverContext
    ) -> LinuxSession:
        ctx.transcript.add_secret(login.secret)
        conn = await ssh_login(target, login.username, login.secret, timeout=ctx.connect_timeout)
        ctx.transcript.write(f"[connected to {target.name} as {login.username}]\n")
        return LinuxSession(login, conn)

    async def change(
        self,
        session: LinuxSession,
        account: AccountRef,
        current: str | None,
        new: str,
        ctx: DriverContext,
    ) -> StepResult:
        if current is None:
            return await self.reconcile(session, account, new, ctx)
        if session.login.username != account.username:
            return StepResult(Outcome.REJECTED_BY_DEVICE, "passwd changes only the logged-in user")
        _check_secret(current)
        _check_secret(new)
        ctx.transcript.add_secret(current)
        ctx.transcript.add_secret(new)
        try:
            process = await session.conn.create_process(
                PASSWD_COMMAND, term_type="vt100", term_size=(200, 50), encoding=None
            )
        except (OSError, asyncssh.Error) as exc:
            return StepResult(Outcome.UNREACHABLE, f"Could not start passwd: {exc}")
        cli = Cli(process, [current, new])
        sent_new = False
        try:
            which, _ = await cli.expect(_CURRENT, _NEW, timeout=ctx.command_timeout)
            if which == 0:
                cli.send(current, enter="\n")
                which, _ = await cli.expect(_NEW, _FAILED, timeout=ctx.command_timeout)
                if which == 1:
                    return self._done(cli, ctx, Outcome.AUTH_FAILED, "current password refused")
            sent_new = True
            cli.send(new, enter="\n")
            which, _ = await cli.expect(_RETYPE, _NEW, _FAILED, timeout=ctx.command_timeout)
            if which != 0:
                cli.send("\x03", enter="")
                return self._done(cli, ctx, Outcome.REJECTED_BY_DEVICE, "new password refused")
            cli.send(new, enter="\n")
            which, _ = await cli.expect(_UPDATED, _NEW, _FAILED, timeout=ctx.command_timeout)
        except CliError as exc:
            # After the new password was typed, the device may or may not have taken it.
            outcome = Outcome.AMBIGUOUS if sent_new else Outcome.UNREACHABLE
            return self._done(cli, ctx, outcome, str(exc))
        finally:
            cli.close()
        if which == 0:
            return self._done(cli, ctx, Outcome.OK, "password updated")
        return self._done(cli, ctx, Outcome.REJECTED_BY_DEVICE, "the device refused the password")

    @staticmethod
    def _done(cli: Cli, ctx: DriverContext, outcome: Outcome, detail: str) -> StepResult:
        ctx.transcript.write(cli.transcript)
        return StepResult(outcome, ctx.transcript.redact(detail), ctx.transcript.take())

    async def persist(self, session: LinuxSession, ctx: DriverContext) -> StepResult:
        return StepResult(Outcome.OK, "not needed on Linux")

    async def reconcile(
        self, session: LinuxSession, account: AccountRef, new: str, ctx: DriverContext
    ) -> StepResult:
        if not _USERNAME.match(account.username):
            return StepResult(Outcome.REJECTED_BY_DEVICE, "unsupported user name")
        _check_secret(new)
        ctx.transcript.add_secret(new)
        ctx.transcript.write(f">>> {CHPASSWD_COMMAND}  (stdin: {account.username}:****)\n")
        try:
            process = await session.conn.create_process(CHPASSWD_COMMAND, encoding=None)
        except (OSError, asyncssh.Error) as exc:
            return StepResult(
                Outcome.UNREACHABLE, f"Could not start chpasswd: {exc}", ctx.transcript.take()
            )
        try:
            process.stdin.write(f"{account.username}:{new}\n".encode())
            process.stdin.write_eof()
            result = await asyncio.wait_for(process.wait(), ctx.command_timeout)
        except (TimeoutError, OSError, asyncssh.Error) as exc:
            return StepResult(Outcome.AMBIGUOUS, f"chpasswd did not answer: {exc}")
        stderr = (result.stderr or b"").decode(errors="replace")
        ctx.transcript.write(stderr)
        if result.exit_status == 0:
            return StepResult(Outcome.OK, "password set", ctx.transcript.take())
        if "password is required" in stderr or "not allowed" in stderr:
            detail = "the reconcile account may not run chpasswd through sudo"
        else:
            detail = f"chpasswd failed (exit {result.exit_status})"
        return StepResult(Outcome.REJECTED_BY_DEVICE, detail, ctx.transcript.take())

    async def verify(
        self, target: TargetRef, account: AccountRef, secret: str, ctx: DriverContext
    ) -> StepResult:
        ctx.transcript.add_secret(secret)
        try:
            conn = await ssh_login(target, account.username, secret, timeout=ctx.connect_timeout)
        except DriverError as exc:
            return exc.result
        conn.close()
        return StepResult(Outcome.OK, f"logged in as {account.username}")
