"""Integration tests against a real PostgreSQL.

Uses WARDX_TEST_DATABASE_URL when set (an empty database), otherwise starts an
embedded PostgreSQL with pgserver. Skipped when neither is available.
"""

from __future__ import annotations

import base64
import os
import secrets

import pytest
from httpx import ASGITransport, AsyncClient

ADMIN_PASSWORD = "Admin-Passw0rd-Test"


@pytest.fixture(scope="session")
def database_url(tmp_path_factory) -> str:
    url = os.environ.get("WARDX_TEST_DATABASE_URL")
    if url:
        return url
    pgserver = pytest.importorskip("pgserver")
    server = pgserver.get_server(tmp_path_factory.mktemp("pg"), cleanup_mode="stop")
    server.psql("CREATE DATABASE wardx_test;")
    return server.get_uri("wardx_test").replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest.fixture(scope="session")
async def app(database_url):
    os.environ.update(
        WARDX_ENVIRONMENT="test",
        WARDX_DATABASE_URL=database_url,
        WARDX_JWT_SECRET=secrets.token_urlsafe(48),
        WARDX_VAULT_KEK=base64.b64encode(secrets.token_bytes(32)).decode(),
        WARDX_BOOTSTRAP_ADMIN_USERNAME="admin",
        WARDX_BOOTSTRAP_ADMIN_PASSWORD=ADMIN_PASSWORD,
        WARDX_APP_ROLE="api_only",
    )
    from src.core.app_factory import create_app, startup
    from src.core.config import get_settings
    from src.core.db import dispose_engine

    get_settings.cache_clear()
    settings = get_settings()
    await startup(settings)
    yield create_app(settings)
    await dispose_engine()


@pytest.fixture(scope="session")
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1") as c:
        yield c


async def login(client: AsyncClient, username: str, password: str) -> dict[str, str]:
    resp = await client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


@pytest.fixture(scope="session")
async def admin(client) -> dict[str, str]:
    return await login(client, "admin", ADMIN_PASSWORD)


@pytest.fixture(scope="session")
async def make_user(client, admin):
    async def _make(username: str, role: str = "user") -> dict[str, str]:
        password = "User-Passw0rd-" + username
        resp = await client.post(
            "/users", headers=admin, json={"username": username, "password": password, "role": role}
        )
        assert resp.status_code == 201, resp.text
        return await login(client, username, password)

    return _make
