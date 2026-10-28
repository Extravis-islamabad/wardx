"""Host-key request shapes."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HostKeyAccept(BaseModel):
    # The fingerprint the administrator compared with the device (SHA256:...). The key is
    # pinned only if the device still presents exactly this one.
    fingerprint: str = Field(min_length=8, max_length=128, pattern=r"^SHA256:[A-Za-z0-9+/=]+$")
