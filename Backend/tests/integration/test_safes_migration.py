"""Migration 012 on a database that already holds accounts: nothing is lost, every account
lands in the Default safe, and the Default safe's role members keep today's access."""

from __future__ import annotations

import shutil
import uuid

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.enums import DEFAULT_SAFE_ID
from src.core.migration_runner import MIGRATIONS_DIR, run_migrations

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_existing_accounts_move_into_the_default_safe(database_url, tmp_path):
    name = f"wardx_migr_{uuid.uuid4().hex[:8]}"
    admin_engine = create_async_engine(database_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(database_url).set(database=name)
    engine = create_async_engine(url)
    try:
        # The schema as it was before safes.
        before = tmp_path / "before"
        before.mkdir()
        for path in MIGRATIONS_DIR.glob("*.sql"):
            if int(path.name.split("_")[0]) < 12:
                shutil.copy(path, before / path.name)
        await run_migrations(engine, before)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO inventory.targets (id, name, address, platform, protocol, port) "
                    "VALUES ('11111111-1111-1111-1111-111111111111', 'old-box', '10.0.0.9', "
                    "'linux', 'ssh', 22)"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO inventory.accounts (target_id, username, requires_approval) "
                    "VALUES ('11111111-1111-1111-1111-111111111111', 'root', false), "
                    "('11111111-1111-1111-1111-111111111111', 'oracle', true)"
                )
            )

        applied = await run_migrations(engine)
        assert "012_safes.sql" in applied
        # Idempotent: running the file again changes nothing.
        async with engine.connect() as conn:
            raw = (await conn.get_raw_connection()).driver_connection
            await raw.execute((MIGRATIONS_DIR / "012_safes.sql").read_text())

        async with engine.connect() as conn:
            rows = (
                await conn.execute(text("SELECT username, safe_id FROM inventory.accounts"))
            ).all()
            members = (
                await conn.execute(
                    text(
                        "SELECT principal_type, principal_key, permissions "
                        "FROM inventory.safe_members WHERE safe_id = :s"
                    ),
                    {"s": DEFAULT_SAFE_ID},
                )
            ).all()
            safes = (await conn.execute(text("SELECT id, name FROM inventory.safes"))).all()
        assert sorted(r.username for r in rows) == ["oracle", "root"]
        assert {r.safe_id for r in rows} == {DEFAULT_SAFE_ID}
        assert safes == [(DEFAULT_SAFE_ID, "Default")]
        got = {(m.principal_type, m.principal_key): set(m.permissions) for m in members}
        base = {"list", "use", "retrieve"}
        assert got == {
            ("role", "user"): base,
            ("role", "auditor"): base,
            ("role", "approver"): base | {"approve"},
            ("role", "admin"): base
            | {"manage_accounts", "manage_members", "view_audit", "approve"},
        }
    finally:
        await engine.dispose()
        async with admin_engine.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        await admin_engine.dispose()
