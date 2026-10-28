"""Fixed-window rate counters shared by every API worker (iam.rate_counters)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import TZ, Base


class RateCounter(Base):
    __tablename__ = "rate_counters"
    __table_args__ = {"schema": "iam"}

    bucket: Mapped[str] = mapped_column(String(160), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(TZ, primary_key=True)
    hits: Mapped[int] = mapped_column(Integer, default=0)
