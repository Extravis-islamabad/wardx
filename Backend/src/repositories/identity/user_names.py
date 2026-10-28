"""Display names (full name, else username) for user ids, for showing named approvers."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import User


async def display_names(session: AsyncSession, keys: Iterable[str | None]) -> dict[str, str]:
    """``{user id string: display name}`` for the keys that are user ids."""
    ids = set()
    for key in keys:
        try:
            ids.add(uuid.UUID(str(key)))
        except ValueError:
            continue
    if not ids:
        return {}
    rows = await session.execute(
        select(User.id, User.full_name, User.username).where(User.id.in_(ids))
    )
    return {str(uid): full or name for uid, full, name in rows.all()}
