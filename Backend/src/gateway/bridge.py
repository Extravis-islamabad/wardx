"""One proxied session: user <-> gateway <-> target, with policy, recording and kill switch."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

import asyncssh
import structlog

from src.gateway.broker import Broker, CloseOrder, Grant
from src.gateway.policy import Bell, Forward, LineTracker, Submit
from src.gateway.recorder import AsciicastRecorder
from src.gateway.recording_writer import RecordingWriter
from src.gateway.target import TargetError, connect

logger = structlog.get_logger(__name__)

_READ = 65536


def banner(text: str) -> bytes:
    return f"\r\n\x1b[1;36m[WardX]\x1b[0m {text}\r\n".encode()


def alert(text: str) -> bytes:
    return f"\r\n\x1b[1;31m[WardX] {text}\x1b[0m\r\n".encode()


class Bridge:
    def __init__(
        self,
        grant: Grant,
        user: asyncssh.SSHServerProcess,
        broker: Broker,
        *,
        open_recording: Callable[[Grant], Awaitable[RecordingWriter]],
        connect_timeout: float,
    ) -> None:
        self.grant = grant
        self.user = user
        self.broker = broker
        self.open_recording = open_recording
        self.writer: RecordingWriter | None = None
        self.connect_timeout = connect_timeout
        self.tracker = LineTracker(restricted=grant.policy.restricted)
        self.recorder: AsciicastRecorder | None = None
        self.target_conn: asyncssh.SSHClientConnection | None = None
        self.target: asyncssh.SSHClientProcess | None = None
        self.bytes_from_target = 0
        self.bytes_from_user = 0
        self._order: CloseOrder | None = None
        self._done = asyncio.Event()

    # ── Kill switch: called by the gateway's watcher ──

    def order_close(self, order: CloseOrder) -> None:
        if self._order is None:
            self._order = order
            self._done.set()

    # ── Lifecycle ──

    async def run(self) -> None:
        status, reason, exit_status = "closed", "Session ended", 0
        term = self.user.get_terminal_type()
        width, height, *_ = self.user.get_terminal_size()
        command = self.user.command
        try:
            # No recording, no session: a failure here ends it before any target contact.
            self.writer = await self.open_recording(self.grant)
            self.recorder = AsciicastRecorder(
                self.writer,
                width=width or 80,
                height=height or 24,
                term=term,
                title=f"{self.grant.actor.username} as {self.grant.account_username}"
                f"@{self.grant.target.name}",
            )
            self._say(banner(self._intro()))
            if command is not None and await self._check_exec(command):
                status, reason, exit_status = "closed", "Command blocked by policy", 126
                return

            self.target_conn = await connect(self.grant, self.broker, self.connect_timeout)
            self.target = await self.target_conn.create_process(
                command,
                term_type=term if term else None,
                term_size=(width, height) if term else None,
                encoding=None,
            )
            pumps = [
                asyncio.create_task(self._from_user()),
                asyncio.create_task(self._from_target(self.target.stdout)),
                asyncio.create_task(self._from_target(self.target.stderr, stderr=True)),
            ]
            done_waiter = asyncio.create_task(self._done.wait())
            target_exit = asyncio.create_task(self.target.wait_closed())
            await asyncio.wait({done_waiter, target_exit}, return_when=asyncio.FIRST_COMPLETED)
            if self._order is not None:
                status, reason = self._order.status, self._order.reason
                self._say(alert(f"{reason}. Disconnecting."))
                exit_status = 255
            else:
                # Let the last output reach the user before closing.
                await asyncio.wait(pumps[1:], timeout=2)
                exit_status = self.target.exit_status or 0
            for task in [*pumps, done_waiter, target_exit]:
                task.cancel()
        except TargetError as exc:
            status, reason, exit_status = "failed", str(exc), 255
            self._say(alert(str(exc)))
        except Exception:
            logger.exception("gateway_session_error", session_id=str(self.grant.session_id))
            status, reason, exit_status = "failed", "Gateway error", 255
            self._say(alert("Gateway error; the session was closed."))
        finally:
            await self._close(status, reason, exit_status)

    def _intro(self) -> str:
        g = self.grant
        lines = (
            f"{g.actor.username} -> {g.account_username}@{g.target.name} ({g.target.address}). "
            f"Session is recorded. Access ends {g.expires_at:%Y-%m-%d %H:%M} UTC."
        )
        if g.policy.restricted:
            lines += " Command policy applies: arrow keys, history and tab completion are off."
        return lines

    async def _check_exec(self, command: str) -> bool:
        """Policy for ``ssh gw 'command'``. True if blocked."""
        rule = self.grant.policy.check(command)
        await self.broker.record_command(
            self.grant,
            offset=self.recorder.elapsed,
            command=command,
            blocked_rule=rule.id if rule else None,
            blocked=rule is not None,
            edited=False,
        )
        if rule is not None:
            self._say(alert(f"Blocked by policy: {rule.description or rule.regex.pattern}"))
        return rule is not None

    # ── Pumps ──

    async def _from_user(self) -> None:
        assert self.target is not None
        interactive = self.user.command is None
        while True:
            try:
                data = await self.user.stdin.read(_READ)
            except asyncssh.TerminalSizeChanged as exc:
                self.target.change_terminal_size(exc.width, exc.height, exc.pixwidth, exc.pixheight)
                self.recorder.resize(exc.width, exc.height)
                continue
            except (asyncssh.BreakReceived, asyncssh.SignalReceived):
                continue
            if not data:
                self.target.stdin.write_eof()
                return
            self.bytes_from_user += len(data)
            if not interactive:
                self.target.stdin.write(data)
                continue
            for event in self.tracker.feed(data):
                if isinstance(event, Forward):
                    self.target.stdin.write(event.data)
                elif isinstance(event, Bell):
                    self._say(b"\a")
                elif isinstance(event, Submit):
                    await self._submit(event)

    async def _submit(self, event: Submit) -> None:
        assert self.target is not None
        line = event.line.strip()
        rule = self.grant.policy.check(event.line) if line else None
        if line:
            # Logged before the Enter reaches the device: a command that runs is
            # always on record, even if the session drops straight after.
            await self.broker.record_command(
                self.grant,
                offset=self.recorder.elapsed,
                command=line,
                blocked_rule=rule.id if rule else None,
                blocked=rule is not None,
                edited=event.edited,
            )
        if rule is None:
            self.target.stdin.write(event.enter)
            return
        # Erase the typed line on the device, tell the user, get a fresh prompt.
        self.target.stdin.write(event.erase)
        self._say(alert(f"Blocked by policy: {rule.description or rule.regex.pattern}"))
        self.recorder.marker(f"blocked: {line}")
        self.target.stdin.write(event.enter)

    async def _from_target(self, stream: asyncssh.SSHReader, *, stderr: bool = False) -> None:
        sink = self.user.stderr if stderr else self.user.stdout
        while True:
            data = await stream.read(_READ)
            if not data:
                return
            self.bytes_from_target += len(data)
            self.recorder.output(data)
            sink.write(data)

    def _say(self, data: bytes) -> None:
        """Write gateway messages to the user (and the recording)."""
        with contextlib.suppress(Exception):
            self.user.stdout.write(data)
        if self.recorder is not None and data != b"\a":
            self.recorder.output(data)

    async def _close(self, status: str, reason: str, exit_status: int) -> None:
        if self.target_conn is not None:
            self.target_conn.close()
        sha256 = size = recording = None
        if self.recorder is not None:
            sha256, size = self.recorder.close()
        if self.writer is not None:
            try:
                stored = await self.writer.close()
                recording = {
                    "recording_key": stored.key,
                    "recording_encrypted": True,
                    "recording_incomplete": False,
                    "recording_ciphertext_sha256": stored.ciphertext_sha256,
                }
            except Exception:
                logger.exception("recording_close_failed", session_id=str(self.grant.session_id))
        try:
            await self.broker.finish(
                self.grant,
                status=status,
                reason=reason,
                recording_path=None,
                recording_sha256=sha256 if recording else None,
                recording_bytes=size if recording else None,
                bytes_from_target=self.bytes_from_target,
                bytes_from_user=self.bytes_from_user,
                recording=recording,
            )
        except Exception:
            logger.exception("gateway_finish_failed", session_id=str(self.grant.session_id))
        with contextlib.suppress(Exception):
            self.user.exit(exit_status)
