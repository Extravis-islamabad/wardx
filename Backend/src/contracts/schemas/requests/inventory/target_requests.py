"""Target request shapes."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.core.enums import Platform, Protocol


class PolicyOverrides(BaseModel):
    """Device-specific password policy caps (docs/phase1/ROTATION.md section 3)."""

    model_config = ConfigDict(extra="forbid")

    length: int | None = Field(None, ge=12, le=128)
    min_length: int | None = Field(None, ge=12, le=128)
    max_length: int | None = Field(None, ge=12, le=128)
    min_classes: int | None = Field(None, ge=1, le=4)
    max_repeat: int | None = Field(None, ge=2, le=128)
    symbols: str | None = Field(None, max_length=32)
    classes: list[str] | None = None
    forbid_leading_symbol: bool | None = None
    forbid_username_substring: bool | None = None


class TargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    address: str = Field(min_length=1, max_length=255)
    platform: Platform
    protocol: Protocol
    port: int | None = Field(None, ge=1, le=65535)
    description: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=50)
    external_ref: str | None = Field(None, max_length=255)
    # Rotation: the per-target safety switch (off by default) and device policy caps.
    rotation_allowed: bool = False
    policy_overrides: PolicyOverrides | None = None
    # Management API (MikroTik): API-SSL port (None = 8729). api_tls false = the device
    # offers only the cleartext API, which is never used for rotation.
    api_port: int | None = Field(None, ge=1, le=65535)
    api_tls: bool = True


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
    rotation_allowed: bool | None = None
    policy_overrides: PolicyOverrides | None = None
    api_port: int | None = Field(None, ge=1, le=65535)
    api_tls: bool | None = None
