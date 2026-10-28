"""One step of a rotation job: outcome, timing and its redacted device transcript."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import TZ, Base, utcnow


class RotationJobStep(Base):
    __tablename__ = "rotation_job_steps"
    __table_args__ = {"schema": "access"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("access.rotation_jobs.id", ondelete="CASCADE")
    )
    step: Mapped[str] = mapped_column(String(30))
    outcome: Mapped[str] = mapped_column(String(24))
    secret_version: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[str | None] = mapped_column(Text)
    transcript: Mapped[str | None] = mapped_column(Text)
    # The device channel the step used (api-ssl, ssh), when it used one.
    channel: Mapped[str | None] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    finished_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
