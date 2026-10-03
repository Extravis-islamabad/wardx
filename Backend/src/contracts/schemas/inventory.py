"""Target and account schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.core.enums import Platform, Protocol, SecretType


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


class TargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    address: str
    platform: str
    protocol: str
    port: int
    description: str | None
    tags: list[str]
    external_ref: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AccountCreate(BaseModel):
    target_id: uuid.UUID
    username: str = Field(min_length=1, max_length=255)
    secret_type: SecretType = SecretType.PASSWORD
    description: str | None = None
    requires_approval: bool = False
    exclusive_checkout: bool = True
    max_checkout_minutes: int = Field(60, ge=1, le=1440)
    # Optional initial secret; can also be set later with PUT /accounts/{id}/secret.
    secret: str | None = Field(None, min_length=1, max_length=16384)


class AccountUpdate(BaseModel):
    description: str | None = None
    requires_approval: bool | None = None
    exclusive_checkout: bool | None = None
    max_checkout_minutes: int | None = Field(None, ge=1, le=1440)


class SecretSet(BaseModel):
    value: str = Field(min_length=1, max_length=16384)


class TargetBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    address: str
    platform: str
    protocol: str


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    target: TargetBrief
    username: str
    secret_type: str
    description: str | None
    has_secret: bool
    secret_version: int
    secret_updated_at: datetime | None
    requires_approval: bool
    exclusive_checkout: bool
    max_checkout_minutes: int
    active_checkouts: int = 0
    created_at: datetime
