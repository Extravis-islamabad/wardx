"""Break-glass request shape."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class EmergencyRevealRequest(BaseModel):
    reason: str = Field(min_length=20, max_length=2000)

    @field_validator("reason")
    @classmethod
    def _meaningful(cls, v: str) -> str:
        if len(v.strip()) < 20:
            raise ValueError("give a reason of at least 20 characters")
        return v.strip()
