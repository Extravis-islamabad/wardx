"""Migration 015 on a database with requires_approval accounts and open requests: those
accounts move to "Default (approval required)" with Default's members and a one-level
policy; open requests continue at level 1 on their safe's policy. Nothing is lost."""

from __future__ import annotations

import shutil
import uuid

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.enums import DEFAULT_APPROVAL_SAFE_ID, DEFAULT_SAFE_ID
from src.core.migration_runner import MIGRATIONS_DIR, run_migrations

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _q(engine, sql: str, **params):
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).all()


async def test_requires_approval_accounts_and_open_requests_migrate(database_url, tmp_path):
    name = f"wardx_migr_{uuid.uuid4().hex[:8]}"
    admin_engine = create_async_engine(database_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_async_engine(make_url(database_url).set(database=name))
    try:
        before = tmp_path / "before"
        before.mkdir()
        for path in MIGRATIONS_DIR.glob("*.sql"):
            if int(path.name.split("_")[0]) < 15:
                shutil.copy(path, before / path.name)
        await run_migrations(engine, before)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO iam.users (id, username, password_hash, role) VALUES "
                    "('22222222-2222-2222-2222-222222222222', 'req', 'x', 'user'), "
                    "('33333333-3333-3333-3333-333333333333', 'appr', 'x', 'approver')"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO inventory.targets (id, name, address, platform, protocol, port) "
                    "VALUES ('11111111-1111-1111-1111-111111111111', 'box', '10.0.0.9', "
                    "'linux', 'ssh', 22)"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO inventory.accounts (id, target_id, username, requires_approval, "
                    "safe_id) VALUES ('44444444-4444-4444-4444-444444444444', "
                    "'11111111-1111-1111-1111-111111111111', 'oracle', true, :d), "
                    "('55555555-5555-5555-5555-555555555555', "
                    "'11111111-1111-1111-1111-111111111111', 'root', false, :d)"
                ),
                {"d": DEFAULT_SAFE_ID},
            )
            await conn.execute(
                text(
                    "INSERT INTO access.requests (id, account_id, requester_id, reason, "
                    "duration_minutes, status, expires_at, decided_by, decided_at) VALUES "
                    "('66666666-6666-6666-6666-666666666666', "
                    "'44444444-4444-4444-4444-444444444444', "
                    "'22222222-2222-2222-2222-222222222222', 'pending one', 30, 'pending', "
                    "NOW() + INTERVAL '1 hour', NULL, NULL)"
                )
            )

        assert "015_approval_workflow.sql" in await run_migrations(engine)
        # Idempotent.
        async with engine.connect() as conn:
            raw = (await conn.get_raw_connection()).driver_connection
            await raw.execute((MIGRATIONS_DIR / "015_approval_workflow.sql").read_text())

        accounts = dict(await _q(engine, "SELECT username, safe_id FROM inventory.accounts"))
        assert accounts == {"oracle": DEFAULT_APPROVAL_SAFE_ID, "root": DEFAULT_SAFE_ID}
        flag = await _q(engine, "SELECT requires_approval FROM inventory.accounts ORDER BY 1")
        assert [f[0] for f in flag] == [False, True]  # the column is kept, untouched

        safe = (
            await _q(
                engine,
                "SELECT name, approval_required, ticket_mode, approval_window_minutes, "
                "approval_multi_use, level_timeout_hours FROM inventory.safes WHERE id = :s",
                s=DEFAULT_APPROVAL_SAFE_ID,
            )
        )[0]
        assert tuple(safe) == ("Default (approval required)", True, "off", 120, False, 24)
        levels = await _q(
            engine,
            "SELECT position, required_approvals, approver_type, approver_key "
            "FROM inventory.safe_approval_levels WHERE safe_id = :s",
            s=DEFAULT_APPROVAL_SAFE_ID,
        )
        assert [tuple(lv) for lv in levels] == [(1, 1, "safe_approvers", None)]
        member_sql = (
            "SELECT principal_type, principal_key, permissions FROM inventory.safe_members "
            "WHERE safe_id = :s ORDER BY 1, 2"
        )
        assert await _q(engine, member_sql, s=DEFAULT_APPROVAL_SAFE_ID) == await _q(
            engine, member_sql, s=DEFAULT_SAFE_ID
        )
        default = await _q(
            engine, "SELECT approval_required FROM inventory.safes WHERE id = :s", s=DEFAULT_SAFE_ID
        )
        assert default[0][0] is False

        request = (
            await _q(
                engine,
                "SELECT status, current_level, policy FROM access.requests WHERE id = :r",
                r="66666666-6666-6666-6666-666666666666",
            )
        )[0]
        assert request.status == "pending" and request.current_level == 1
        assert request.policy["levels"] == [
            {
                "position": 1,
                "required_approvals": 1,
                "approver_type": "safe_approvers",
                "approver_key": None,
            }
        ]
    finally:
        await engine.dispose()
        async with admin_engine.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        await admin_engine.dispose()
