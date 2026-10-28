"""Target request shapes."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.core.enums import Platform, Protocol


class TargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    address: str = Field(min_length=1, max_length=255)
    platform: Platform
    protocol: Protocol
    port: int | None = Field(None, ge=1, le=65535)
    description: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=50)
    external_ref: str | None = Field(None, max_length=255)


class TargetUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    address: str | None = Field(None, min_length=1, max_length=255)
    platform: Platform | None = None
    protocol: Protocol | None = None
    port: int | None = Field(None, ge=1, le=65535)
    description: str | None = None
    tags: list[str] | None = Field(None, max_length=50)
    external_ref: str | None = Field(None, max_length=255)
    is_active: bool | None = None
