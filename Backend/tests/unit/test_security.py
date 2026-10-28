import uuid
from datetime import timedelta

import pytest

from src.contracts.schemas.requests.identity.user_requests import UserCreate
from src.core.security import create_token, decode_token, hash_password, verify_password
from src.errors.exceptions import UnauthorizedError

SECRET = "x" * 48


async def test_password_hash_round_trip():
    h = await hash_password("Correct-Horse-9")
    assert h.startswith("$argon2id$")
    assert await verify_password(h, "Correct-Horse-9")
    assert not await verify_password(h, "wrong")
    assert not await verify_password("not-a-hash", "x")


def test_token_round_trip_and_type_check():
    uid = uuid.uuid4()
    tok = create_token(
        secret=SECRET, user_id=uid, token_version=3, token_type="access", ttl=timedelta(minutes=5)
    )
    claims = decode_token(tok, secret=SECRET, expected_type="access")
    assert claims["sub"] == str(uid) and claims["tv"] == 3
    with pytest.raises(UnauthorizedError):
        decode_token(tok, secret=SECRET, expected_type="refresh")


def test_expired_and_forged_tokens_rejected():
    uid = uuid.uuid4()
    expired = create_token(
        secret=SECRET, user_id=uid, token_version=0, token_type="access", ttl=timedelta(seconds=-1)
    )
    with pytest.raises(UnauthorizedError, match="expired"):
        decode_token(expired, secret=SECRET, expected_type="access")
    forged = create_token(
        secret="y" * 48, user_id=uid, token_version=0, token_type="access", ttl=timedelta(minutes=5)
    )
    with pytest.raises(UnauthorizedError):
        decode_token(forged, secret=SECRET, expected_type="access")


@pytest.mark.parametrize("pw", ["short1A!", "alllowercaseletters", "ALLUPPER12345"])
def test_weak_passwords_rejected(pw):
    with pytest.raises(ValueError):
        UserCreate(username="bob", password=pw)


def test_strong_password_accepted():
    assert UserCreate(username="bob", password="Str0ng-enough-pw").username == "bob"
