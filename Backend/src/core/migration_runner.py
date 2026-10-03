"""Applies pending numbered SQL migrations (``NNN_name.sql``) in order.

Each file runs in its own transaction and is recorded in ``_schema_migrations``.
A cluster-wide advisory lock keeps concurrent starts (API + scheduler) from
applying the same file twice. Files are written to be idempotent anyway.
"""

from __future__ import annotations

import re
from pathlib import Path

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = structlog.get_logger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
_NUMBERED = re.compile(r"^(\d+)_.+\.sql$")
_LOCK_KEY = 0x5741_5244_0001  # "WARD" + 1

_CREATE_TRACKING = """
CREATE TABLE IF NOT EXISTS _schema_migrations (
    filename   VARCHAR(255) PRIMARY KEY,
    applied_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
)
"""


def pending_files(directory: Path, applied: set[str]) -> list[Path]:
    files = [p for p in directory.iterdir() if _NUMBERED.match(p.name)]
    files.sort(key=lambda p: (int(_NUMBERED.match(p.name).group(1)), p.name))
    return [p for p in files if p.name not in applied]


async def run_migrations(engine: AsyncEngine, directory: Path = MIGRATIONS_DIR) -> list[str]:
    applied_now: list[str] = []
    async with engine.connect() as conn:
        await conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _LOCK_KEY})
        try:
            await conn.execute(text(_CREATE_TRACKING))
            await conn.commit()
            applied = set(
                (await conn.execute(text("SELECT filename FROM _schema_migrations"))).scalars()
            )
            # End SQLAlchemy's transaction so each file's transaction below is top level.
            await conn.commit()
            for path in pending_files(directory, applied):
                # The raw asyncpg connection runs a multi-statement script in one
                # simple-protocol call, so $$-quoted function bodies stay intact.
                raw = (await conn.get_raw_connection()).driver_connection
                async with raw.transaction():
                    await raw.execute(path.read_text())
                    await raw.execute(
                        "INSERT INTO _schema_migrations (filename) VALUES ($1)", path.name
                    )
                applied_now.append(path.name)
                logger.info("migration_applied", file=path.name)
        finally:
            await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_KEY})
            await conn.commit()
    return applied_now
