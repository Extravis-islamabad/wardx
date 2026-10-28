"""Database session providers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.dependencies.tenant import TenantDep


async def get_tenant_session(tenant: TenantDep) -> AsyncIterator[AsyncSession]:
    """A session on the request tenant's database.

    Services own their transactions and commit when a unit of work is done; a
    session that leaves a request uncommitted is rolled back.
    """
    async with tenant.session_factory()() as session:
        try:
            yield session
        finally:
            if session.in_transaction():
                await session.rollback()


SQLSessionDep = Annotated[AsyncSession, Depends(get_tenant_session)]
