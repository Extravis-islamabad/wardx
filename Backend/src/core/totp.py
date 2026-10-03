"""RFC 6238 TOTP (HMAC-SHA1, 30-second steps, 6 digits) — what authenticator apps speak."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

STEP_SECONDS = 30
DIGITS = 6
# Accept the previous and next step too, for clock drift between phone and server.
DRIFT_STEPS = 1


def new_seed() -> str:
    """160-bit seed, base32 without padding (the form apps accept)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(seed: str) -> bytes:
    return base64.b32decode(seed + "=" * (-len(seed) % 8), casefold=True)


def code_at(seed: str, step: int) -> str:
    digest = hmac.new(_key(seed), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def match_step(
    seed: str, code: str, *, now: float | None = None, after: int | None = None
) -> int | None:
    """The step ``code`` belongs to, if valid and newer than ``after``; else None."""
    code = code.strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    step = current_step(now)
    for candidate in range(step - DRIFT_STEPS, step + DRIFT_STEPS + 1):
        if after is not None and candidate <= after:
            continue
        if hmac.compare_digest(code_at(seed, candidate), code):
            return candidate
    return None


def provisioning_uri(seed: str, *, account: str, issuer: str = "WardX") -> str:
    label = quote(f"{issuer}:{account}")
    query = urlencode({"secret": seed, "issuer": issuer, "digits": DIGITS, "period": STEP_SECONDS})
    return f"otpauth://totp/{label}?{query}"


# ── Recovery codes ──


def new_recovery_codes(count: int = 10) -> list[str]:
    """Ten codes like ``K7PQ-9MZX-T2WD``: 60 bits each, easy to read and type."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(alphabet) for _ in range(12))
        codes.append(f"{raw[:4]}-{raw[4:8]}-{raw[8:]}")
    return codes


def normalise_recovery(code: str) -> str:
    return code.strip().upper().replace("-", "").replace(" ", "")


def hash_recovery(code: str) -> str:
    return hashlib.sha256(normalise_recovery(code).encode()).hexdigest()
