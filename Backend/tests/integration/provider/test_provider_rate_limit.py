"""The per-app fetch rate limit holds across API workers (CREDENTIAL_PROVIDER.md §1, §10).

The cross-worker test starts a second, real API worker (``uvicorn main:app`` in its own
process, on 127.0.0.1 and a free port, against the same test database) and fires
fetches at both workers at once: together they serve exactly the app's limit.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import sys
import time
from pathlib import Path

import httpx
import pytest

from src.core.tenant import current_tenant
from src.services.provider.rate_limit_service import RateLimitService
from tests.integration.provider.provider_support import (
    caller,
    code,
    create_app,
    fetch,
    fetchable,
    token,
)
from tests.integration.safes_support import tag

pytestmark = pytest.mark.asyncio(loop_scope="session")

BACKEND = Path(__file__).resolve().parents[3]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _clear_of_window_edge(seconds: int = 12) -> None:
    """Fixed windows are per minute: start well inside one, so all hits land in it."""
    left = 60 - time.time() % 60
    if left < seconds:
        await asyncio.sleep(left + 0.5)


@contextlib.asynccontextmanager
async def second_worker():
    port = _free_port()
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        cwd=BACKEND,
        env={**os.environ, "WARDX_APP_ROLE": "api_only"},
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        async with httpx.AsyncClient(base_url=f"{base}/api/v1", timeout=30) as c:
            for _ in range(150):
                with contextlib.suppress(httpx.TransportError):
                    if (await c.get(f"{base}/health")).status_code == 200:
                        break
                await asyncio.sleep(0.2)
            else:
                raise AssertionError("the second API worker did not start")
            yield c
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), 15)
        except TimeoutError:
            proc.kill()
            await proc.wait()


async def test_rate_limit_holds_across_two_api_workers(app, client, admin):
    limit = 12
    created = await create_app(client, admin, ip="127.0.0.1", rate_limit_per_minute=limit)
    _, target, _ = await fetchable(client, admin, created)
    async with second_worker() as other, caller(app, "127.0.0.1") as local:
        headers = await token(local, created)  # one token, valid on every worker
        await _clear_of_window_edge()
        ref = target["external_ref"]
        results = await asyncio.gather(
            *[fetch(local, headers, external_ref=ref) for _ in range(limit)],
            *[fetch(other, headers, external_ref=ref) for _ in range(limit)],
        )
    statuses = [r.status_code for r in results]
    assert statuses.count(200) == limit, statuses
    assert statuses.count(429) == limit, statuses
    limited = [r for r in results if r.status_code == 429]
    assert {code(r) for r in limited} == {"rate_limited"}
    assert all(int(r.headers["retry-after"]) >= 1 for r in limited)
    # Both workers authenticated the same token and counted into the same window: with
    # per-process counting they would have served 2 x limit.
    assert set(statuses[:limit]) <= {200, 429} and set(statuses[limit:]) <= {200, 429}


async def test_counter_is_exact_under_concurrent_sessions():
    """Many sessions hitting one bucket at once: exactly ``limit`` are allowed."""
    rate = RateLimitService(current_tenant().session_factory())
    bucket = f"test:{tag()}"
    await _clear_of_window_edge(5)
    results = await asyncio.gather(*[rate.hit(bucket, 7) for _ in range(25)])
    assert [ok for ok, _ in results].count(True) == 7


async def test_fetches_over_the_limit_are_refused_and_audited(app, client, admin):
    created = await create_app(client, admin, rate_limit_per_minute=2)
    _, target, _ = await fetchable(client, admin, created)
    async with caller(app, created.ip) as c:
        headers = await token(c, created)
        await _clear_of_window_edge()
        got = [await fetch(c, headers, external_ref=target["external_ref"]) for _ in range(3)]
    assert [r.status_code for r in got] == [200, 200, 429]
    from tests.integration.rotation.rotation_support import sql

    rows = await sql(
        "SELECT details->>'error_code' AS err FROM audit.events "
        "WHERE action = 'secret.app_fetch' AND actor_id = :a AND outcome = 'failure'",
        a=created.id,
    )
    assert [r["err"] for r in rows] == ["rate_limited"]
