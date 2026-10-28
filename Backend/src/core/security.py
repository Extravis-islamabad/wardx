"""Password hashing (argon2id) and JWT access / refresh tokens."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Literal

import jwt
from anyio import to_thread
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from src.errors.exceptions import UnauthorizedError

# "mfa": proves the password step only; exchanged for real tokens with a valid code.
TokenType = Literal["access", "refresh", "mfa"]
_ALGORITHM = "HS256"
_ISSUER = "wardx"

_hasher = PasswordHasher()


async def hash_password(password: str) -> str:
    # argon2 is deliberately slow; keep it off the event loop.
    return await to_thread.run_sync(_hasher.hash, password)


def _verify(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


async def verify_password(password_hash: str, password: str) -> bool:
    return await to_thread.run_sync(_verify, password_hash, password)


@lru_cache
def _dummy_hash() -> str:
    return _hasher.hash(uuid.uuid4().hex)


async def burn_password_check(password: str) -> None:
    """Spend the same time as a real check, so unknown usernames are not revealed by timing."""
    await verify_password(_dummy_hash(), password)


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def create_token(
    *, secret: str, user_id: uuid.UUID, token_version: int, token_type: TokenType, ttl: timedelta
) -> str:
    now = datetime.now(UTC)
    payload = {
        "iss": _ISSUER,
        "sub": str(user_id),
        "tv": token_version,
        "typ": token_type,
        "iat": now,
        "exp": now + ttl,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def decode_token(token: str, *, secret: str, expected_type: TokenType) -> dict:
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            options={"require": ["exp", "iat", "sub", "typ", "tv"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Token expired") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid token") from exc
    if claims.get("typ") != expected_type:
        raise UnauthorizedError("Invalid token type")
    return claims


# ── Application identity tokens (docs/phase1/CREDENTIAL_PROVIDER.md §2) ──

APP_TOKEN_TYPE = "app"
APP_TOKEN_AUDIENCE = "wardx-credential-provider"


def _app_token_key(secret: str) -> bytes:
    """A key of its own, derived from the JWT secret, so an app token can never verify as a
    user token or the other way round, even before the type and audience checks."""
    return hmac.new(secret.encode(), b"wardx-app-token-v1", hashlib.sha256).digest()


def create_app_token(
    *,
    secret: str,
    app_id: uuid.UUID,
    token_version: int,
    secret_id: uuid.UUID,
    ttl: timedelta,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "iss": _ISSUER,
        "aud": APP_TOKEN_AUDIENCE,
        "sub": str(app_id),
        "tv": token_version,
        "typ": APP_TOKEN_TYPE,
        # The client secret it was issued for: revoking that secret kills the token.
        "sid": str(secret_id),
        "iat": now,
        "exp": now + ttl,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _app_token_key(secret), algorithm=_ALGORITHM)


def decode_app_token(token: str, *, secret: str) -> dict:
    """The claims of a valid app token; ``ValueError`` for anything else (never says why
    to the caller: the provider answers ``invalid_token`` whatever the reason)."""
    try:
        claims = jwt.decode(
            token,
            _app_token_key(secret),
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            audience=APP_TOKEN_AUDIENCE,
            options={"require": ["exp", "iat", "sub", "typ", "tv", "sid", "jti", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise ValueError("invalid app token") from exc
    if claims.get("typ") != APP_TOKEN_TYPE:
        raise ValueError("invalid app token type")
    return claims
