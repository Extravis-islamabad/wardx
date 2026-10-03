import base64
from urllib.parse import parse_qs, urlparse

from src.core import totp

# RFC 6238 appendix B: ASCII seed "12345678901234567890" (SHA-1), 8-digit codes.
RFC_SEED = base64.b32encode(b"12345678901234567890").decode()
RFC_VECTORS = {
    59: "94287082",
    1111111109: "07081804",
    1234567890: "89005924",
    2000000000: "69279037",
}


def test_rfc6238_vectors_last_six_digits():
    for t, expected in RFC_VECTORS.items():
        assert totp.code_at(RFC_SEED, t // 30) == expected[-6:]


def test_match_accepts_one_step_of_drift_and_rejects_more():
    seed = totp.new_seed()
    now = 1_800_000_000.0
    step = totp.current_step(now)
    assert totp.match_step(seed, totp.code_at(seed, step), now=now) == step
    assert totp.match_step(seed, totp.code_at(seed, step - 1), now=now) == step - 1
    assert totp.match_step(seed, totp.code_at(seed, step + 1), now=now) == step + 1
    assert totp.match_step(seed, totp.code_at(seed, step - 2), now=now) is None


def test_used_step_cannot_be_replayed():
    seed = totp.new_seed()
    now = 1_800_000_000.0
    step = totp.current_step(now)
    code = totp.code_at(seed, step)
    assert totp.match_step(seed, code, now=now, after=step) is None
    assert totp.match_step(seed, code, now=now, after=step - 1) == step


def test_malformed_codes_rejected():
    seed = totp.new_seed()
    for bad in ("", "12345", "1234567", "abcdef", "12 34 5x"):
        assert totp.match_step(seed, bad) is None
    assert totp.match_step(seed, " " + totp.code_at(seed, totp.current_step()) + " ") is not None


def test_provisioning_uri_is_what_authenticator_apps_scan():
    uri = totp.provisioning_uri("ABCDEF", account="alice")
    parsed = urlparse(uri)
    assert parsed.scheme == "otpauth" and parsed.netloc == "totp"
    assert parsed.path == "/WardX%3Aalice"
    assert parse_qs(parsed.query) == {
        "secret": ["ABCDEF"],
        "issuer": ["WardX"],
        "digits": ["6"],
        "period": ["30"],
    }


def test_recovery_codes_are_unique_readable_and_hash_normalised():
    codes = totp.new_recovery_codes()
    assert len(set(codes)) == 10
    assert all(len(c) == 14 and c.count("-") == 2 for c in codes)
    assert not any(ch in "01IO" for c in codes for ch in c.replace("-", ""))
    c = codes[0]
    assert totp.hash_recovery(c) == totp.hash_recovery(c.lower().replace("-", " "))
