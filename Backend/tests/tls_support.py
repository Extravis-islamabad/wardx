"""A local TLS server speaking a small RouterOS API dialect, for API-SSL tests.

Certificates are generated per test run. The key material is written only under
``lab/.secrets/`` (gitignored, directory 0700, files 0600) for the moment it takes
``ssl`` to load it, then deleted: nothing about it is committed or kept.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import shutil
import ssl
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from src.transport.routeros_api import cert_fingerprint, encode_sentence

SECRETS = Path(__file__).resolve().parents[2] / "lab" / ".secrets"


@dataclass(frozen=True)
class TestCert:
    __test__ = False  # not a test class

    cert_pem: str
    key_pem: str = field(repr=False)

    @property
    def fingerprint(self) -> str:
        return cert_fingerprint(ssl.PEM_cert_to_DER_cert(self.cert_pem))


def make_cert(name: str, *, days: int = 30, expired: bool = False) -> TestCert:
    """A self-signed P-256 server certificate (like a device's own API-SSL certificate)."""
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = dt.datetime.now(dt.UTC)
    start, end = (
        (now - dt.timedelta(days=10), now - dt.timedelta(days=1))
        if expired
        else (
            now - dt.timedelta(minutes=5),
            now + dt.timedelta(days=days),
        )
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(end)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return TestCert(
        cert.public_bytes(serialization.Encoding.PEM).decode(),
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
    )


def server_context(cert: TestCert) -> ssl.SSLContext:
    """A server context for this certificate; the key touches disk only under lab/.secrets."""
    SECRETS.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="wardx-test-tls-", dir=SECRETS))
    try:
        os.chmod(folder, 0o700)
        cert_file, key_file = folder / "cert.pem", folder / "key.pem"
        for path, text in ((cert_file, cert.cert_pem), (key_file, cert.key_pem)):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write(text)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert_file, key_file)
        return ctx
    finally:
        shutil.rmtree(folder, ignore_errors=True)


async def read_word(reader: asyncio.StreamReader) -> str | None:
    first = (await reader.readexactly(1))[0]
    if first < 0x80:
        n = first
    elif first < 0xC0:
        n = ((first & 0x3F) << 8) | (await reader.readexactly(1))[0]
    elif first < 0xE0:
        n = ((first & 0x1F) << 16) | int.from_bytes(await reader.readexactly(2), "big")
    elif first < 0xF0:
        n = ((first & 0x0F) << 24) | int.from_bytes(await reader.readexactly(3), "big")
    else:
        n = int.from_bytes(await reader.readexactly(4), "big")
    return (await reader.readexactly(n)).decode() if n else None


Handler = Callable[[list[str], dict], list[list[str]] | None]
_DONE = [["!done"]]


def _trap(message: str) -> list[list[str]]:
    return [["!trap", f"=message={message}"], ["!done"]]


@dataclass
class ApiServer:
    """A TLS listener answering API sentences like RouterOS (/login, /password,
    /user/print, /user/set) from ``users``, or with ``handler`` (None = drop the
    connection). Records every sentence it received."""

    cert: TestCert
    users: dict[str, str] = field(default_factory=dict, repr=False)
    handler: Handler | None = None
    received: list[list[str]] = field(default_factory=list)
    connections: int = 0
    port: int = 0
    _server: asyncio.base_events.Server | None = None

    def default(self, sentence: list[str], state: dict) -> list[list[str]] | None:
        attrs = dict(w[1:].partition("=")[::2] for w in sentence[1:] if w.startswith("="))
        command, user = sentence[0], state.get("user")
        if command == "/login":
            if self.users.get(attrs.get("name")) == attrs.get("password"):
                state["user"] = attrs["name"]
                return _DONE
            return _trap("invalid user name or password (6)")
        if user is None:
            return [["!fatal", "not logged in"]]
        if command == "/password":
            if self.users.get(user) != attrs.get("old-password"):
                return _trap("failure: Bad old password!")
            self.users[user] = attrs["new-password"]
            return _DONE
        names = sorted(self.users)
        if command == "/user/print":
            wanted = next((q[6:] for q in sentence[1:] if q.startswith("?name=")), None)
            return [
                ["!re", f"=.id=*{i}", f"=name={n}"]
                for i, n in enumerate(names)
                if wanted in (None, n)
            ] + _DONE
        if command == "/user/set":
            index = int(attrs.get(".id", "*-1")[1:])
            if not 0 <= index < len(names):
                return _trap("no such item (4)")
            self.users[names[index]] = attrs["password"]
            return _DONE
        return _trap("no such command prefix")

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        state: dict = {}
        try:
            while True:
                sentence: list[str] = []
                while (word := await read_word(reader)) is not None:
                    sentence.append(word)
                if not sentence:
                    continue
                self.received.append(sentence)
                replies = (self.handler or self.default)(sentence, state)
                if replies is None:
                    break
                for reply in replies:
                    writer.write(encode_sentence(reply))
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, ssl.SSLError):
            pass
        finally:
            writer.close()

    async def start(self) -> ApiServer:
        self._server = await asyncio.start_server(
            self._serve, "127.0.0.1", 0, ssl=server_context(self.cert)
        )
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
