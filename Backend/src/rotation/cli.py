"""Expect-style conversation with a device CLI over an interactive SSH channel.

Everything sent and received is kept as a transcript for the rotation job,
with each secret replaced by ``****`` before it is stored.
"""

from __future__ import annotations

import asyncio
import re

import asyncssh

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-Z\\-_]|\r")
_TRANSCRIPT_LIMIT = 20_000


class CliError(Exception):
    """The device did not answer as expected; message is safe to store (redacted)."""


class Cli:
    def __init__(self, process: asyncssh.SSHClientProcess, secrets: list[str]) -> None:
        self._proc = process
        self._secrets = [s for s in secrets if s]
        self._buffer = ""
        self._log: list[str] = []

    @classmethod
    async def open(cls, conn: asyncssh.SSHClientConnection, secrets: list[str]) -> Cli:
        # Wide terminal: long config lines must not wrap or be truncated.
        process = await conn.create_process(term_type="vt100", term_size=(511, 50), encoding=None)
        return cls(process, secrets)

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "****")
        return text

    @property
    def transcript(self) -> str:
        text = "".join(self._log)
        return text[-_TRANSCRIPT_LIMIT:]

    def send(self, line: str, *, enter: str = "\r") -> None:
        self._proc.stdin.write((line + enter).encode())
        self._log.append(f">>> {self.redact(line)}\n")

    async def expect(self, *patterns: str, timeout: float = 15) -> tuple[int, str]:  # noqa: ASYNC109
        """Wait until one pattern matches the output; return (which, text up to the match)."""
        compiled = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in patterns]
        try:
            async with asyncio.timeout(timeout):
                while True:
                    for i, rx in enumerate(compiled):
                        match = rx.search(self._buffer)
                        if match:
                            text = self._buffer[: match.end()]
                            self._buffer = self._buffer[match.end() :]
                            return i, text
                    chunk = await self._proc.stdout.read(4096)
                    if not chunk:
                        raise CliError(f"Connection closed while waiting for {patterns}")
                    decoded = _ANSI.sub("", chunk.decode(errors="replace"))
                    self._buffer += decoded
                    self._log.append(self.redact(decoded))
        except TimeoutError as exc:
            tail = self.redact(self._buffer[-300:])
            raise CliError(f"Timed out waiting for {patterns}; last output: {tail!r}") from exc

    def close(self) -> None:
        self._proc.close()
