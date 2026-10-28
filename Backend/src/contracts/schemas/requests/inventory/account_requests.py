"""Account request shapes."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from src.core.enums import SecretType


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
