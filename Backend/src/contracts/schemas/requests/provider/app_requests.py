"""Application identity request shapes (apps.manage)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

_NAME = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"


class AppCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=_NAME)
    description: str | None = Field(None, max_length=2000)
    enabled: bool = True
    # CIDRs or single addresses. Empty = no access until one is added.
    ip_allowlist: list[str] = Field(default_factory=list, max_length=100)
    rate_limit_per_minute: int = Field(600, ge=1, le=100000)
    # Optional expiry of the first client secret.
    secret_expires_at: datetime | None = None


class AppUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100, pattern=_NAME)
    description: str | None = Field(None, max_length=2000)
    enabled: bool | None = None
    ip_allowlist: list[str] | None = Field(None, max_length=100)
    rate_limit_per_minute: int | None = Field(None, ge=1, le=100000)


class AppSecretCreate(BaseModel):
    expires_at: datetime | None = None
