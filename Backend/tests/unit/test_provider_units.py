"""Credential provider building blocks: token separation, source IP, SNMP documents."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from starlette.requests import Request

from src.core.client_ip import in_networks, parse_networks, source_ip
from src.core.security import (
    create_app_token,
    create_token,
    decode_app_token,
    decode_token,
)
from src.errors.exceptions import UnauthorizedError
from src.services.inventory.snmp_secrets import InvalidSnmpSecret, snmp_document
from src.services.provider.credential_service import shape_secret, version_id

KEY = "k" * 48


def _app_token(**kw) -> str:
    return create_app_token(
        secret=KEY,
        app_id=uuid.uuid4(),
        token_version=0,
        secret_id=uuid.uuid4(),
        ttl=kw.get("ttl", timedelta(minutes=5)),
    )


def test_app_and_user_tokens_never_cross():
    app_token = _app_token()
    user_token = create_token(
        secret=KEY,
        user_id=uuid.uuid4(),
        token_version=0,
        token_type="access",
        ttl=timedelta(minutes=5),
    )
    assert decode_app_token(app_token, secret=KEY)["typ"] == "app"
    with pytest.raises(UnauthorizedError):
        decode_token(app_token, secret=KEY, expected_type="access")
    with pytest.raises(ValueError):
        decode_app_token(user_token, secret=KEY)
    with pytest.raises(ValueError):
        decode_app_token(_app_token(), secret="x" * 48)
    with pytest.raises(ValueError):
        decode_app_token(_app_token(ttl=timedelta(seconds=-1)), secret=KEY)


def _request(peer: str, xff: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "client": (peer, 1234), "headers": headers})


def test_source_ip_believes_forwarded_for_only_from_trusted_proxies():
    assert source_ip(_request("10.0.0.5", "1.2.3.4"), []) == "10.0.0.5"
    assert source_ip(_request("10.0.0.5", "1.2.3.4"), ["10.0.0.0/24"]) == "1.2.3.4"
    # The right-most untrusted hop counts; anything the client wrote to its left does not.
    assert source_ip(_request("10.0.0.5", "6.6.6.6, 1.2.3.4, 10.0.0.9"), ["10.0.0.0/24"]) == (
        "1.2.3.4"
    )
    assert source_ip(_request("10.0.0.5", "garbage"), ["10.0.0.0/24"]) is None
    assert source_ip(_request("10.0.0.5"), ["10.0.0.0/24"]) == "10.0.0.5"


def test_allowlist_matching():
    nets = parse_networks(["10.1.0.0/16", "2001:db8::/32"])
    assert in_networks("10.1.2.3", nets) and in_networks("::ffff:10.1.2.3", nets)
    assert in_networks("2001:db8::1", nets)
    assert not in_networks("10.2.0.1", nets) and not in_networks(None, nets)
    assert not in_networks("10.1.2.3", [])
    with pytest.raises(ValueError):
        parse_networks(["nope"])


def test_snmp_documents_and_shapes():
    doc = snmp_document("snmp_v2c", {"version": "2c", "community": "ro"})
    assert shape_secret("snmp_v2c", doc) == {"version": "2c", "community": "ro"}
    with pytest.raises(InvalidSnmpSecret):
        snmp_document("snmp_v2c", {"version": "2c", "community": "  "})
    with pytest.raises(InvalidSnmpSecret):
        snmp_document("snmp_v3", {"version": "3", "security_name": "x", "security_level": "bad"})
    assert shape_secret("password", "   ") == {}
    assert shape_secret("ssh_key", "KEY") == {"private_key": "KEY"}
    assert shape_secret("snmp_v3", "not json") == {}


def test_version_id_is_stable_per_version():
    account = uuid.uuid4()
    assert version_id(account, 3) == version_id(account, 3) != version_id(account, 4)
