"""A tiny SSH 'router' for gateway tests: echoes like a CLI and records what it ran."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import asyncssh


@dataclass
class FakeDevice:
    username: str
    password: str
    prompt: str = "fake-rtr# "
    executed: list[str] = field(default_factory=list)
    logins: list[tuple[str, str]] = field(default_factory=list)
    host_key: asyncssh.SSHKey = field(
        default_factory=lambda: asyncssh.generate_private_key("ssh-ed25519")
    )
    server: asyncssh.SSHAcceptor | None = None

    @property
    def port(self) -> int:
        return self.server.get_port()

    def output(self, line: str) -> str:
        if line == "show version":
            return "FakeOS 1.0 uptime 42 days\r\n"
        return f"% ran: {line}\r\n" if line else ""

    async def start(self) -> None:
        device = self

        class _Server(asyncssh.SSHServer):
            def begin_auth(self, username: str) -> bool:
                return True

            def password_auth_supported(self) -> bool:
                return True

            def validate_password(self, username: str, password: str) -> bool:
                device.logins.append((username, password))
                return username == device.username and password == device.password

        self.server = await asyncssh.create_server(
            _Server,
            "127.0.0.1",
            0,
            server_host_keys=[self.host_key],
            process_factory=self._session,
            encoding=None,
            line_editor=False,
        )

    async def stop(self) -> None:
        self.server.close()
        await self.server.wait_closed()

    async def _session(self, process: asyncssh.SSHServerProcess) -> None:
        if process.command is not None:
            self.executed.append(process.command)
            process.stdout.write(self.output(process.command).encode())
            process.exit(0)
            return
        process.stdout.write(self.prompt.encode())
        line = bytearray()
        try:
            while True:
                try:
                    data = await process.stdin.read(1024)
                except asyncssh.TerminalSizeChanged:
                    continue
                if not data:
                    break
                for b in data:
                    if b in (0x7F, 0x08):
                        if line:
                            line.pop()
                            process.stdout.write(b"\x08 \x08")
                    elif b == 0x0D:
                        text = line.decode(errors="replace").strip()
                        line.clear()
                        process.stdout.write(b"\r\n")
                        if text == "exit":
                            process.exit(0)
                            return
                        if text:
                            self.executed.append(text)
                        process.stdout.write((self.output(text) + self.prompt).encode())
                    elif b >= 0x20:
                        line.append(b)
                        process.stdout.write(bytes([b]))
                await asyncio.sleep(0)
        except (asyncssh.BreakReceived, asyncssh.SignalReceived):
            pass
        process.exit(0)
