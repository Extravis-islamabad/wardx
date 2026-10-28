"""Database session providers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_session

# Services own their transactions and commit when a unit of work is done; a
# session that leaves a request uncommitted is rolled back.
SQLSessionDep = Annotated[AsyncSession, Depends(get_session)]
