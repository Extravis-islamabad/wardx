"""Shared setup for rotation tests: a fake device behind the 'generic' platform, accounts
on it, and a worker that runs the engine on demand."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from src.core.config import get_settings
from src.core.db import session_factory
from src.dependencies.rotation import build_rotation_scheduler_service, build_rotation_store
from src.dependencies.vault import build_vault_service
from src.rotation.drivers.registry import DriverRegistry, default_registry
from src.services.inventory.account_service import ACCOUNT_SECRET
from src.services.rotation.rotation_engine import RotationEngine, SimulatedCrash
from src.services.rotation.rotation_worker import RotationWorker
from tests.integration.rotation.fake_driver import FAKE_PLATFORM, FakeDevice, FakeDriver
from tests.integration.safes_support import tag

START = "Start-Passw0rd-1x"  # gitleaks:allow
PINNED = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeLabKeyForTestsOnly000000000000000 fake"


async def sql(statement: str, **params):
    async with session_factory()() as s:
        result = await s.execute(text(statement), params)
        rows = result.mappings().all() if result.returns_rows else None
        await s.commit()
        return rows


async def one(statement: str, **params) -> dict:
    rows = await sql(statement, **params)
    assert rows, statement
    return dict(rows[0])


async def read_secret(account_id, version: int) -> str:
    async with session_factory()() as s:
        return await build_vault_service(s).read(
            owner_type=ACCOUNT_SECRET, owner_id=uuid.UUID(str(account_id)), version=version
        )


class CrashAt:
    """A checkpoint that kills the engine once, at the named state."""

    def __init__(self, name: str | None = None, action=None) -> None:
        self.name = name
        self.action = action
        self.seen: list[str] = []

    async def __call__(self, name: str) -> None:
        self.seen.append(name)
        if name == self.name:
            self.name = None
            if self.action is not None:
                await self.action()
                return
            raise SimulatedCrash(name)


class Lab:
    def __init__(self, client, admin) -> None:
        self.client = client
        self.admin = admin
        self.device = FakeDevice()
        self.driver = FakeDriver(self.device)
        self.registry = DriverRegistry()
        self.registry.register(self.driver)

    def use(self, driver: FakeDriver) -> None:
        self.driver = driver
        self.registry.register(driver)
        default_registry()._drivers[FAKE_PLATFORM] = driver

    async def safe(self, **policy) -> str:
        """A new safe the admin role works in (seeded directly: no self-grant via the API),
        with this rotation policy."""
        resp = await self.client.post(
            "/safes", headers=self.admin, json={"name": f"rot-safe-{tag()}"}
        )
        assert resp.status_code == 201, resp.text
        safe_id = resp.json()["data"]["id"]
        await sql(
            "INSERT INTO inventory.safe_members (safe_id, principal_type, principal_key, "
            "permissions) VALUES (:s, 'role', 'admin', "
            "ARRAY['list','use','retrieve','manage_accounts','view_audit'])",
            s=safe_id,
        )
        if policy:
            resp = await self.client.put(
                f"/safes/{safe_id}/rotation-policy", headers=self.admin, json=policy
            )
            assert resp.status_code == 200, resp.text
        return safe_id

    async def target(self, *, allowed: bool = True, protocol: str = "ssh") -> dict:
        resp = await self.client.post(
            "/targets",
            headers=self.admin,
            json={
                "name": f"rot-{tag()}",
                "address": "192.0.2.10",
                "platform": FAKE_PLATFORM,
                "protocol": protocol,
                "rotation_allowed": allowed,
            },
        )
        assert resp.status_code == 201, resp.text
        target = resp.json()["data"]
        await sql(
            "UPDATE inventory.targets SET ssh_host_key = :k WHERE id = :i", k=PINNED, i=target["id"]
        )
        return target

    async def account(
        self,
        *,
        password: str = START,
        target: dict | None = None,
        safe_id: str | None = None,
        username: str | None = None,
        on_device: bool = True,
    ) -> dict:
        target = target or await self.target()
        username = username or f"wardx_rot_{tag()}"
        body = {"target_id": target["id"], "username": username, "secret": password}
        if safe_id:
            body["safe_id"] = safe_id
        resp = await self.client.post("/accounts", headers=self.admin, json=body)
        assert resp.status_code == 201, resp.text
        if on_device:
            self.device.passwords[username] = password
        return {**resp.json()["data"], "target": target}

    async def request(self, account_id: str, op: str = "rotate", **body) -> dict:
        resp = await self.client.post(
            f"/accounts/{account_id}/{op}",
            headers=self.admin,
            json={"reason": "rotation test", **body},
        )
        assert resp.status_code == 202, resp.text
        return resp.json()["data"]

    def worker(self, checkpoint=None, *, enabled: bool = True) -> RotationWorker:
        engine = RotationEngine(
            session_factory(),
            build_rotation_store,
            self.registry,
            enabled=enabled,
            checkpoint=checkpoint,
        )
        return RotationWorker(session_factory(), engine, worker_id=f"test-{tag()}")

    async def tick(self, checkpoint=None, *, enabled: bool = True) -> int:
        """Release waits, then run what is due (one claim round)."""
        async with session_factory()() as s:
            await build_rotation_scheduler_service(s).release_waiting()
        return await self.worker(checkpoint, enabled=enabled).run_once()

    async def run(self, job_id: str, checkpoint=None, *, rounds: int = 6) -> dict:
        """Run the job to a final state, skipping back-off waits and expired leases."""
        for _ in range(rounds):
            await self.due_now(job_id)
            try:
                await self.tick(checkpoint)
            except SimulatedCrash:
                await self.expire_lease(job_id)
            job = await self.job(job_id)
            if job["status"] not in (
                "pending",
                "running",
                "candidate_stored",
                "device_changed",
                "persisted",
                "waiting_release",
            ):
                return job
        return await self.job(job_id)

    async def due_now(self, job_id: str) -> None:
        await sql(
            "UPDATE access.rotation_jobs SET not_before = NOW() - INTERVAL '1 second' "
            "WHERE id = :i",
            i=job_id,
        )

    async def expire_lease(self, job_id: str) -> None:
        await sql(
            "UPDATE access.rotation_jobs SET lease_until = NOW() - INTERVAL '1 second' "
            "WHERE id = :i AND lease_until IS NOT NULL",
            i=job_id,
        )

    async def job(self, job_id: str) -> dict:
        resp = await self.client.get(f"/rotation/jobs/{job_id}", headers=self.admin)
        assert resp.status_code == 200, resp.text
        return resp.json()["data"]

    async def state(self, account_id: str) -> dict:
        return await one(
            "SELECT secret_version, sync_status, rotation_status, last_rotation_status, "
            "last_verified_at, risk_flags FROM inventory.accounts WHERE id = :i",
            i=account_id,
        )

    async def labels(self, account_id: str) -> dict[int, str]:
        rows = await sql(
            "SELECT version, status FROM vault.secrets WHERE owner_id = :i", i=account_id
        )
        return {r["version"]: r["status"] for r in rows}

    async def current(self, account_id: str) -> str:
        return await read_secret(account_id, (await self.state(account_id))["secret_version"])

    async def alerts(self, account_id: str) -> list[str]:
        rows = await sql(
            "SELECT kind FROM security.alerts WHERE object_id = :i ORDER BY created_at",
            i=account_id,
        )
        return [r["kind"] for r in rows]


@pytest.fixture(name="rotlab")
async def rotlab_fixture(client, admin):
    """Rotation switched on, the fake driver registered for 'generic'."""
    settings = get_settings()
    previous = settings.rotation_enabled
    settings.rotation_enabled = True
    env = Lab(client, admin)
    with default_registry().override(FAKE_PLATFORM, env.driver):
        yield env
    settings.rotation_enabled = previous
