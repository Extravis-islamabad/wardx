"""Transitional shim: the ORM account lookup access_service still uses.

New code uses AccountService (src/services/inventory/account_service.py).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors.exceptions import NotFoundError
from src.models import Account
from src.services.inventory.account_service import ACCOUNT_SECRET

__all__ = ["ACCOUNT_SECRET", "get_account"]


async def get_account(
    session: AsyncSession, account_id: uuid.UUID, *, lock: bool = False
) -> Account:
    stmt = select(Account).where(Account.id == account_id).execution_options(populate_existing=True)
    if lock:
        stmt = stmt.with_for_update(of=Account)
    account = (await session.execute(stmt)).scalar_one_or_none()
    if account is None:
        raise NotFoundError("Account not found")
    return account
