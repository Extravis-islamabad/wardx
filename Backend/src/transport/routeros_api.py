"""RouterOS API over TLS (API-SSL), with the device certificate pinned.

Trust comes only from the certificate WardX pinned for the target: it is the single
trust anchor of a CERT_REQUIRED context (partial chains allowed, so a self-signed
device certificate is accepted when it IS the pinned one), and the SHA-256 fingerprint
of the presented DER certificate must equal the pin before anything is sent. Host name
checking is off because identity is the pin, not a name. Certificate verification is
never disabled; the only unverified read is ``fetch_certificate``, which shows an
administrator the certificate to compare before pinning, and re-reads what a device
presented after a failed pin check. Neither sends a single API word.

Protocol: sentences of length-prefixed words ending with an empty word; replies are
``!re`` (a row), ``!done``, ``!trap`` (an error, followed by ``!done``), ``!empty``
(no rows, RouterOS 7.18+) or ``!fatal`` (the session ends).
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import ssl
from dataclasses import dataclass, field

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
# What RouterOS answers to a wrong name or password (``invalid user name or password (6)``).
_BAD_LOGIN = "invalid user name or password"


class ApiError(Exception):
    """The device answered with !trap or !fatal; ``message`` is its text."""

    def __init__(self, message: str, *, fatal: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.fatal = fatal


class CertificateMismatch(Exception):
    """The device's certificate is not the pinned one, or failed verification
    (nothing was sent). ``presented`` is its fingerprint when it could be read;
    ``verify_message`` is OpenSSL's reason when verification failed."""

    def __init__(self, presented: str | None, verify_message: str | None = None) -> None:
        super().__init__(presented or "unknown certificate")
        self.presented = presented
        self.verify_message = verify_message


class Unavailable(Exception):
    """API-SSL is not usable. ``timed_out``: no answer at all (maybe the device is down);
    otherwise it refused, closed or did not speak TLS (the service is off)."""

    def __init__(self, message: str, *, timed_out: bool = False) -> None:
        super().__init__(message)
        self.timed_out = timed_out


class ConnectionLost(Exception):
    """The connection failed after a command was written: the device may have run it."""


def cert_fingerprint(der: bytes) -> str:
    """SHA-256 of the DER certificate, as AA:BB:... (how browsers and OpenSSL show it)."""
    return ":".join(f"{b:02X}" for b in hashlib.sha256(der).digest())


def normalise_fingerprint(value: str | None) -> str | None:
    """AA:BB:... from any common spelling (RouterOS prints 64 lower-case hex digits with
    no separators); None if it is not a SHA-256 fingerprint."""
    digits = re.sub(r"[\s:]", "", value or "").lower()
    if not _HEX64.match(digits):
        return None
    return ":".join(digits[i : i + 2] for i in range(0, 64, 2)).upper()


async def fetch_certificate(host: str, port: int, timeout: float) -> tuple[str, str]:  # noqa: ASYNC109
    """(PEM, fingerprint) of the certificate a device presents, for an admin to compare.

    Reads the certificate during the handshake only; nothing else is sent.
    """
    try:
        pem = await asyncio.wait_for(
            asyncio.to_thread(ssl.get_server_certificate, (host, port), timeout=timeout),
            timeout + 1,
        )
    except TimeoutError as exc:
        raise Unavailable(f"API-SSL on {host}:{port} did not answer", timed_out=True) from exc
    except (OSError, ssl.SSLError) as exc:
        raise Unavailable(f"API-SSL on {host}:{port} did not answer: {exc}") from exc
    return pem, cert_fingerprint(ssl.PEM_cert_to_DER_cert(pem))


def pinned_context(pinned_pem: str) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False  # identity is the pinned certificate, not a host name
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    ctx.load_verify_locations(cadata=pinned_pem)
    return ctx


def encode_length(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    if n < 0x4000:
        return (n | 0x8000).to_bytes(2, "big")
    if n < 0x200000:
        return (n | 0xC00000).to_bytes(3, "big")
    if n < 0x10000000:
        return (n | 0xE0000000).to_bytes(4, "big")
    return b"\xf0" + n.to_bytes(4, "big")


def encode_sentence(words: list[str]) -> bytes:
    """Length-prefixed words and the terminating empty word. A word may never be empty
    (that would end the sentence early and run the rest as another command)."""
    out = bytearray()
    for word in words:
        raw = word.encode()
        if not raw:
            raise ValueError("an API word cannot be empty")
        out += encode_length(len(raw)) + raw
    return bytes(out) + b"\x00"


@dataclass
class ApiConnection:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    timeout: float
    # Words sent and reply kinds, with values of secret attributes masked (transcript).
    log: list[str] = field(default_factory=list)

    async def _read_length(self) -> int:
        first = (await self.reader.readexactly(1))[0]
        if first < 0x80:
            return first
        if first < 0xC0:
            return ((first & 0x3F) << 8) | (await self.reader.readexactly(1))[0]
        if first < 0xE0:
            rest = await self.reader.readexactly(2)
            return ((first & 0x1F) << 16) | int.from_bytes(rest, "big")
        if first < 0xF0:
            rest = await self.reader.readexactly(3)
            return ((first & 0x0F) << 24) | int.from_bytes(rest, "big")
        if first == 0xF0:
            return int.from_bytes(await self.reader.readexactly(4), "big")
        raise ApiError(f"unexpected control byte 0x{first:02X} from the device", fatal=True)

    async def _read_sentence(self) -> list[str]:
        words: list[str] = []
        while True:
            n = await self._read_length()
            if n == 0:
                return words
            words.append((await self.reader.readexactly(n)).decode(errors="replace"))

    async def call(
        self,
        command: str,
        attrs: dict[str, str] | None = None,
        queries: list[str] | None = None,
        *,
        secret_attrs: tuple[str, ...] = (),
    ) -> list[dict[str, str]]:
        """Send one command; its !re rows, or ApiError on !trap / !fatal.

        ConnectionLost when the connection fails after the command was written (the
        device may have run it); nothing is retried here.
        """
        if not command.startswith("/"):
            raise ValueError("an API command starts with /")
        attrs = attrs or {}
        if any(not k or "=" in k for k in attrs):
            raise ValueError("attribute names cannot be empty or contain '='")
        words = [command] + [f"={k}={v}" for k, v in attrs.items()] + (queries or [])
        payload = encode_sentence(words)
        shown = (
            [command]
            + [f"={k}={'****' if k in secret_attrs else v}" for k, v in attrs.items()]
            + (queries or [])
        )
        self.log.append(">>> " + " ".join(shown))
        rows: list[dict[str, str]] = []
        trap: str | None = None
        try:
            self.writer.write(payload)
            async with asyncio.timeout(self.timeout):
                await self.writer.drain()
                while True:
                    sentence = await self._read_sentence()
                    if not sentence:
                        continue
                    kind, body = sentence[0], sentence[1:]
                    attrs_in = {}
                    for w in body:
                        if w.startswith("="):
                            key, _, value = w[1:].partition("=")
                            attrs_in[key] = value
                    if kind == "!re":
                        rows.append(attrs_in)
                    elif kind == "!trap":
                        trap = attrs_in.get("message", "error")
                    elif kind == "!fatal":
                        message = body[0] if body else "fatal"
                        self.log.append(f"<<< !fatal {message}")
                        raise ApiError(message, fatal=True)
                    elif kind == "!done":
                        self.log.append(f"<<< {'!trap ' + trap if trap else '!done'}")
                        if trap is not None:
                            raise ApiError(trap)
                        return rows
                    # !empty and anything newer: no rows; wait for !done.
        except ApiError:
            raise
        except (TimeoutError, OSError, EOFError, ssl.SSLError) as exc:
            self.log.append(f"<<< connection lost ({type(exc).__name__})")
            raise ConnectionLost(f"{command}: {type(exc).__name__}") from exc

    async def close(self) -> None:
        self.writer.close()
        try:
            await asyncio.wait_for(self.writer.wait_closed(), 3)
        except (OSError, TimeoutError, ssl.SSLError):
            pass


async def open_api_ssl(
    host: str,
    port: int,
    *,
    pinned_pem: str,
    pinned_fingerprint: str,
    timeout: float,  # noqa: ASYNC109
) -> ApiConnection:
    """Connect over TLS and check the pin; nothing is sent before the pin holds.

    Unavailable: refused, closed, timed out or no TLS service. CertificateMismatch:
    anything about the identity (another certificate, or one that fails verification).
    """
    pinned = normalise_fingerprint(pinned_fingerprint)
    if not pinned_pem or pinned is None:
        raise CertificateMismatch(None, "no certificate is pinned")
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=pinned_context(pinned_pem)), timeout
        )
    except ssl.SSLCertVerificationError as exc:
        presented = None
        try:
            _, presented = await fetch_certificate(host, port, timeout)
        except Unavailable:
            pass
        raise CertificateMismatch(presented, exc.verify_message) from exc
    except ssl.SSLError as exc:
        # A TLS failure that is not about the certificate (the port answers in cleartext,
        # or resets mid-handshake) means API-SSL is not usable there.
        raise Unavailable(f"TLS handshake with {host}:{port} failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise Unavailable(f"API-SSL on {host}:{port} did not answer", timed_out=True) from exc
    except OSError as exc:
        raise Unavailable(f"API-SSL on {host}:{port} is not available: {exc!r}") from exc
    conn = ApiConnection(reader, writer, timeout)
    der = writer.get_extra_info("ssl_object").getpeercert(binary_form=True)
    presented = cert_fingerprint(der) if der else None
    if presented != pinned:
        await conn.close()
        raise CertificateMismatch(presented)
    return conn


async def login(conn: ApiConnection, username: str, password: str) -> bool:
    """True when the device accepts the credential, False when it refuses it.

    Exactly one /login per call. Any other answer (another trap, a fatal error, a lost
    connection) raises: it proves nothing about the password.
    """
    try:
        await conn.call(
            "/login", {"name": username, "password": password}, secret_attrs=("password",)
        )
    except ApiError as exc:
        if not exc.fatal and _BAD_LOGIN in exc.message.lower():
            return False
        raise
    return True
