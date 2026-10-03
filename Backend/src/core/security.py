"""Password hashing (argon2id) and JWT access / refresh tokens."""

from __future__ import annotations

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
