"""Redaction of transcripts and argv safety of the Linux driver (ROTATION.md §1 rule 4).

A scripted SSH connection stands in for the device: it records every command line the
driver starts and everything written to stdin, and plays the passwd dialogue.
"""

from __future__ import annotations

import asyncio

from src.rotation.drivers.base import (
    AccountRef,
    Credential,
    DriverContext,
    Outcome,
    Transcript,
)
from src.rotation.drivers.linux import CHPASSWD_COMMAND, LinuxDriver, LinuxSession

CURRENT = "Cur-Rent-Pass-123"  # gitleaks:allow
NEW = "New-Pass-Word-456789"  # gitleaks:allow


class _Stdin:
    def __init__(self, proc):
        self.proc = proc

    def write(self, data: bytes) -> None:
        self.proc.stdin_data.append(data)
        self.proc.on_input(data)

    def write_eof(self) -> None:
        self.proc.eof = True


class _Stdout:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()

    async def read(self, n: int) -> bytes:
        return await self.queue.get()


class _Completed:
    def __init__(self, status: int, stderr: bytes) -> None:
        self.exit_status = status
        self.stderr = stderr


class FakeProcess:
    def __init__(self, script: list[bytes], exit_status: int = 0, stderr: bytes = b""):
        self.stdin_data: list[bytes] = []
        self.stdin = _Stdin(self)
        self.stdout = _Stdout()
        self.script = list(script)
        self.eof = False
        self._status, self._stderr = exit_status, stderr
        if self.script:
            self.stdout.queue.put_nowait(self.script.pop(0))

    def on_input(self, data: bytes) -> None:
        if self.script:
            self.stdout.queue.put_nowait(self.script.pop(0))

    async def wait(self):
        return _Completed(self._status, self._stderr)

    def close(self) -> None:
        pass


class FakeConn:
    def __init__(self, process: FakeProcess) -> None:
        self.process = process
        self.commands: list[str] = []

    async def create_process(self, command=None, **kwargs):
        self.commands.append(command)
        return self.process

    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass


PASSWD_OK = [
    b"Changing password for wardx_rot_a.\r\nCurrent password: ",
    b"\r\nNew password: ",
    b"\r\nRetype new password: ",
    # A careless device echoing the password must still be redacted.
    b"\r\npasswd: password updated successfully (" + NEW.encode() + b")\r\n",
]


def _ctx() -> DriverContext:
    return DriverContext(Transcript([]), connect_timeout=2, command_timeout=2)


async def test_self_change_types_secrets_at_prompts_never_in_argv():
    conn = FakeConn(FakeProcess(PASSWD_OK))
    session = LinuxSession(Credential("wardx_rot_a", CURRENT), conn)
    result = await LinuxDriver().change(session, AccountRef(1, "wardx_rot_a"), CURRENT, NEW, _ctx())
    assert result.outcome == Outcome.OK, result
    assert all(CURRENT not in c and NEW not in c for c in conn.commands)
    assert conn.commands == ["env LC_ALL=C passwd"]
    typed = b"".join(conn.process.stdin_data).decode()
    assert typed == f"{CURRENT}\n{NEW}\n{NEW}\n"
    for text in (result.transcript, result.detail):
        assert CURRENT not in text and NEW not in text
    assert "****" in result.transcript


async def test_device_refusing_the_new_password_is_rejected_not_ambiguous():
    script = [PASSWD_OK[0], PASSWD_OK[1], b"\r\nBAD PASSWORD: too simple\r\nNew password: "]
    conn = FakeConn(FakeProcess(script))
    session = LinuxSession(Credential("wardx_rot_a", CURRENT), conn)
    result = await LinuxDriver().change(session, AccountRef(1, "wardx_rot_a"), CURRENT, NEW, _ctx())
    assert result.outcome == Outcome.REJECTED_BY_DEVICE


async def test_connection_lost_after_the_new_password_is_ambiguous():
    script = [PASSWD_OK[0], PASSWD_OK[1], PASSWD_OK[2], b""]  # EOF after the retype
    conn = FakeConn(FakeProcess(script))
    session = LinuxSession(Credential("wardx_rot_a", CURRENT), conn)
    result = await LinuxDriver().change(session, AccountRef(1, "wardx_rot_a"), CURRENT, NEW, _ctx())
    assert result.outcome == Outcome.AMBIGUOUS


async def test_reconcile_sends_the_password_on_stdin_only():
    conn = FakeConn(FakeProcess([], exit_status=0))
    session = LinuxSession(Credential("wardx_rot_admin", CURRENT), conn)
    result = await LinuxDriver().reconcile(session, AccountRef(1, "wardx_rot_a"), NEW, _ctx())
    assert result.outcome == Outcome.OK
    assert conn.commands == [CHPASSWD_COMMAND]
    assert NEW not in CHPASSWD_COMMAND
    assert b"".join(conn.process.stdin_data) == f"wardx_rot_a:{NEW}\n".encode()
    assert conn.process.eof
    assert NEW not in result.transcript


async def test_reconcile_refuses_user_names_that_would_break_chpasswd_input():
    conn = FakeConn(FakeProcess([]))
    session = LinuxSession(Credential("wardx_rot_admin", CURRENT), conn)
    for bad in ("root:x", "a\nroot", "-rf", ""):
        result = await LinuxDriver().reconcile(session, AccountRef(1, bad), NEW, _ctx())
        assert result.outcome == Outcome.REJECTED_BY_DEVICE
    assert conn.commands == []


async def test_sudo_refusal_is_reported_without_the_secret():
    conn = FakeConn(FakeProcess([], exit_status=1, stderr=b"sudo: a password is required\n"))
    session = LinuxSession(Credential("wardx_rot_admin", CURRENT), conn)
    result = await LinuxDriver().reconcile(session, AccountRef(1, "wardx_rot_a"), NEW, _ctx())
    assert result.outcome == Outcome.REJECTED_BY_DEVICE
    assert "sudo" in result.detail and NEW not in result.transcript


def test_transcript_redacts_every_secret_longest_first():
    t = Transcript(["abc", "abcdef"])
    t.add_secret("zzz")
    t.write("x abcdef y abc z zzz")
    assert t.take() == "x **** y **** z ****"
