"""The RouterOS API-SSL client (src/transport/routeros_api.py) against a local TLS server.

The server's certificate is generated per run (tests/tls_support.py); nothing is
pinned, stored or committed. The core property: nothing is sent to a device until its
certificate is verified against the pin AND its fingerprint equals the pin.
"""

from __future__ import annotations

import asyncio
import socket
import ssl

import pytest

from src.transport import routeros_api as api
from tests.tls_support import ApiServer, make_cert

PW = "Unit-Api-Passw0rd-1"  # gitleaks:allow - a test-only value for a local fake server


@pytest.fixture(scope="module")
def certs():
    return make_cert("device-a"), make_cert("device-b")


@pytest.fixture
async def server(certs):
    srv = await ApiServer(certs[0], users={"wardx_rot_unit": PW}).start()
    yield srv
    await srv.stop()


async def _open(srv: ApiServer, cert=None, fingerprint=None):
    cert = cert or srv.cert
    return await api.open_api_ssl(
        "127.0.0.1",
        srv.port,
        pinned_pem=cert.cert_pem,
        pinned_fingerprint=fingerprint or cert.fingerprint,
        timeout=5.0,
    )


# ── word encoding ──


@pytest.mark.parametrize(
    ("n", "size"),
    [
        (0, 1),
        (0x7F, 1),
        (0x80, 2),
        (0x3FFF, 2),
        (0x4000, 3),
        (0x1FFFFF, 3),
        (0x200000, 4),
        (0xFFFFFFF, 4),
        (0x10000000, 5),
    ],
)
async def test_length_encoding_round_trips(n, size):
    encoded = api.encode_length(n)
    assert len(encoded) == size
    reader = asyncio.StreamReader()
    reader.feed_data(encoded)
    conn = api.ApiConnection(reader, None, 1.0)  # type: ignore[arg-type]
    assert await conn._read_length() == n


def test_length_encoding_boundaries():
    assert api.encode_length(0x7F) == b"\x7f"
    assert api.encode_length(0x80) == b"\x80\x80"
    assert api.encode_length(0x3FFF) == b"\xbf\xff"
    assert api.encode_length(0x4000) == b"\xc0\x40\x00"
    assert api.encode_length(0x200000) == b"\xe0\x20\x00\x00"
    assert api.encode_length(0x10000000) == b"\xf0\x10\x00\x00\x00"


def test_sentence_encoding_and_empty_word_refused():
    assert api.encode_sentence(["/login", "=name=a"]) == b"\x06/login\x07=name=a\x00"
    long = "=x=" + "y" * 200
    assert api.encode_sentence([long]).startswith(b"\x80\xcb")
    # An empty word would end the sentence and run the rest as another command.
    with pytest.raises(ValueError):
        api.encode_sentence(["/user/print", "", "/system/reboot"])


async def test_a_reserved_control_byte_is_fatal():
    reader = asyncio.StreamReader()
    reader.feed_data(b"\xf8")
    with pytest.raises(api.ApiError) as err:
        await api.ApiConnection(reader, None, 1.0)._read_length()  # type: ignore[arg-type]
    assert err.value.fatal


def test_fingerprint_spellings():
    hexdigits = "65cd1c13b42ef04723944fd22ae077bf0abaea765b955a2df017a3c19ebf79b9"
    canonical = api.normalise_fingerprint(hexdigits)
    assert canonical.startswith("65:CD:1C") and len(canonical) == 95
    assert api.normalise_fingerprint(canonical.lower()) == canonical
    assert api.normalise_fingerprint(" " + canonical + "\n") == canonical
    for bad in ("", "SHA256:abc", hexdigits[:-2], hexdigits + "00", "zz" * 32, None):
        assert api.normalise_fingerprint(bad) is None


# ── the pin is checked before anything is sent ──


async def test_pinned_certificate_connects_and_logs_in(server):
    conn = await _open(server)
    try:
        assert await api.login(conn, "wardx_rot_unit", PW) is True
        assert await api.login(conn, "wardx_rot_unit", PW + "x") is False
    finally:
        await conn.close()
    assert [s[0] for s in server.received] == ["/login", "/login"]
    # The transcript never holds the password.
    assert all(PW not in line for line in conn.log)
    assert conn.log[0] == ">>> /login =name=wardx_rot_unit =password=****"


async def test_another_certificate_is_refused_before_any_word(server, certs):
    other = certs[1]
    with pytest.raises(api.CertificateMismatch) as err:
        await _open(server, cert=other)
    # It reports what the device presented, and sent nothing.
    assert err.value.presented == server.cert.fingerprint
    assert server.received == []


async def test_a_fingerprint_that_differs_from_the_pin_is_refused(server, certs):
    """The certificate verifies against the pinned PEM, but the pinned fingerprint names
    another certificate: refused after the handshake, before any word."""
    with pytest.raises(api.CertificateMismatch) as err:
        await _open(server, fingerprint=certs[1].fingerprint)
    assert err.value.presented == server.cert.fingerprint
    assert server.received == []


async def test_no_pin_means_no_connection(server):
    for pem, fingerprint in (("", server.cert.fingerprint), (server.cert.cert_pem, "nope")):
        with pytest.raises(api.CertificateMismatch):
            await api.open_api_ssl(
                "127.0.0.1", server.port, pinned_pem=pem, pinned_fingerprint=fingerprint, timeout=2
            )
    assert server.connections == 0


async def test_an_expired_pinned_certificate_fails_verification():
    expired = make_cert("device-old", expired=True)
    srv = await ApiServer(expired).start()
    try:
        with pytest.raises(api.CertificateMismatch) as err:
            await _open(srv)
        assert err.value.presented == expired.fingerprint
        assert "expired" in (err.value.verify_message or "")
        assert srv.received == []
    finally:
        await srv.stop()


# ── what "not available" looks like ──


async def test_a_closed_port_is_unavailable_not_timed_out(certs):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with pytest.raises(api.Unavailable) as err:
        await api.open_api_ssl(
            "127.0.0.1",
            port,
            pinned_pem=certs[0].cert_pem,
            pinned_fingerprint=certs[0].fingerprint,
            timeout=2,
        )
    assert err.value.timed_out is False


async def test_a_cleartext_service_is_unavailable(certs):
    """The plain API (8728) answers in cleartext: the TLS handshake fails, nothing sent."""
    seen: list[bytes] = []

    async def plain(reader, writer):
        seen.append(await reader.read(5))
        writer.write(b"\x05!done\x00")
        await writer.drain()
        writer.close()

    srv = await asyncio.start_server(plain, "127.0.0.1", 0)
    port = srv.sockets[0].getsockname()[1]
    try:
        with pytest.raises(api.Unavailable) as err:
            await api.open_api_ssl(
                "127.0.0.1",
                port,
                pinned_pem=certs[0].cert_pem,
                pinned_fingerprint=certs[0].fingerprint,
                timeout=2,
            )
        assert err.value.timed_out is False
        assert seen and seen[0][:1] == b"\x16"  # only a TLS ClientHello was sent
    finally:
        srv.close()


async def test_a_silent_service_times_out(certs):
    async def silent(reader, writer):
        await asyncio.sleep(5)
        writer.close()

    srv = await asyncio.start_server(silent, "127.0.0.1", 0)
    port = srv.sockets[0].getsockname()[1]
    try:
        with pytest.raises(api.Unavailable) as err:
            await api.open_api_ssl(
                "127.0.0.1",
                port,
                pinned_pem=certs[0].cert_pem,
                pinned_fingerprint=certs[0].fingerprint,
                timeout=0.5,
            )
        assert err.value.timed_out is True
    finally:
        srv.close()


# ── replies and errors ──


async def test_rows_traps_empty_and_fatal(server):
    def handler(sentence, state):
        if sentence[0] == "/user/print":
            return [["!re", "=.id=*2", "=name=wardx_rot_unit"], ["!re", "=name=x=y"], ["!done"]]
        if sentence[0] == "/none":
            return [["!empty"], ["!done"]]
        if sentence[0] == "/password":
            return [["!trap", "=message=failure: Bad old password!"], ["!done"]]
        if sentence[0] == "/quit":
            return [["!fatal", "session terminated on request"]]
        return server.default(sentence, state)

    server.handler = handler
    conn = await _open(server)
    try:
        rows = await conn.call("/user/print", queries=["?name=wardx_rot_unit"])
        assert rows == [{".id": "*2", "name": "wardx_rot_unit"}, {"name": "x=y"}]
        assert await conn.call("/none") == []
        with pytest.raises(api.ApiError) as err:
            await conn.call(
                "/password",
                {"old-password": PW, "new-password": PW + "2"},
                secret_attrs=("old-password", "new-password"),
            )
        assert err.value.message == "failure: Bad old password!" and not err.value.fatal
        with pytest.raises(api.ApiError) as err:
            await conn.call("/quit")
        assert err.value.fatal
    finally:
        await conn.close()
    assert all(PW not in line for line in conn.log)
    assert server.received[2] == ["/password", f"=old-password={PW}", f"=new-password={PW}2"]


async def test_login_raises_on_anything_but_a_clear_refusal(server):
    """Only 'invalid user name or password' means refused; anything else proves nothing."""
    server.handler = lambda s, state: [["!fatal", "too many sessions"]]
    conn = await _open(server)
    try:
        with pytest.raises(api.ApiError):
            await api.login(conn, "wardx_rot_unit", PW)
    finally:
        await conn.close()


async def test_a_dropped_connection_after_sending_is_connection_lost(server):
    server.handler = lambda s, state: None  # the device closes without answering
    conn = await _open(server)
    try:
        with pytest.raises(api.ConnectionLost):
            await conn.call("/user/set", {".id": "*2", "password": PW}, secret_attrs=("password",))
    finally:
        await conn.close()
    assert server.received[0][0] == "/user/set"
    assert any("connection lost" in line for line in conn.log)
    assert all(PW not in line for line in conn.log)


async def test_command_shape_is_checked_before_sending(server):
    conn = await _open(server)
    try:
        with pytest.raises(ValueError):
            await conn.call("user/print")
        with pytest.raises(ValueError):
            await conn.call("/user/set", {"pass=word": "x"})
    finally:
        await conn.close()
    assert server.received == []


async def test_fetch_certificate_reads_without_sending(server):
    pem, fingerprint = await api.fetch_certificate("127.0.0.1", server.port, 3)
    assert fingerprint == server.cert.fingerprint
    assert ssl.PEM_cert_to_DER_cert(pem) == ssl.PEM_cert_to_DER_cert(server.cert.cert_pem)
    assert server.received == []
