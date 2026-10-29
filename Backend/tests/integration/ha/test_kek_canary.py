"""KEK canary (HA_DR.md §6, D10): a node with the wrong KEK refuses to start."""

from __future__ import annotations

import base64
import os

import pytest

from src.core.db import session_factory
from src.keys.file_provider import FileKeyProvider
from src.keys.runtime import key_provider
from src.repositories.keys.kek_canary_repository import KekCanaryRepository
from src.services.keys.kek_canary_service import KekCanaryService, KekMismatch
from tests.integration.ha.ha_support import execute, scalar

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _check(provider) -> str:
    async with session_factory()() as session:
        return await KekCanaryService(KekCanaryRepository(session), provider).check()


def _random_provider(retired: bytes | None = None) -> FileKeyProvider:
    return FileKeyProvider(os.urandom(32), [retired] if retired else [])


async def test_canary_exists_after_startup_and_opens_with_the_right_kek(app):
    assert await scalar("SELECT count(*) FROM keystore.kek_canary") == 1
    assert await _check(key_provider()) == "ok"


async def test_wrong_kek_refuses(app):
    with pytest.raises(KekMismatch, match="Refusing to start"):
        await _check(_random_provider())


async def test_existing_install_gets_canary_only_with_a_matching_kek(app):
    await execute("DELETE FROM keystore.kek_canary")
    # An existing install (tenant keys exist) and the wrong KEK: no canary is created.
    with pytest.raises(KekMismatch, match="existing tenant keys"):
        await _check(_random_provider())
    assert await scalar("SELECT count(*) FROM keystore.kek_canary") == 0
    # The right KEK creates it on first start.
    assert await _check(key_provider()) == "created"
    assert await _check(key_provider()) == "ok"


async def test_kek_rotation_rewraps_the_canary(app):
    current = key_provider()
    raw = base64.b64decode(os.environ["WARDX_VAULT_KEK"])
    rotated = _random_provider(retired=raw)
    try:
        assert await _check(rotated) == "rewrapped"
        assert await scalar("SELECT kek_id FROM keystore.kek_canary") == rotated.active_key_id
        assert await _check(rotated) == "ok"
        # The old KEK alone no longer opens it: rotate back for the rest of the run.
        with pytest.raises(KekMismatch):
            await _check(current)
    finally:
        back = FileKeyProvider(raw, [])
        async with session_factory()() as session:
            repo = KekCanaryRepository(session)
            value = await rotated.unwrap(await repo.get(), b"wardx-kek-canary|v1")
            await repo.rewrap(await back.wrap(value, b"wardx-kek-canary|v1"))
            await repo.commit()
    assert await _check(current) == "ok"
