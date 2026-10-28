"""Declarative base and column helpers shared by every model.

Tables are created by the SQL files in migrations/, never by metadata.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import DeclarativeBase


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


TZ = TIMESTAMP(timezone=True)
