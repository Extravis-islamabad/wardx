"""Account request shapes."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from src.core.enums import SecretType


class AccountCreate(BaseModel):
    target_id: uuid.UUID
    # The safe the account goes into; omitted = the Default safe.
    safe_id: uuid.UUID | None = None
    username: str = Field(min_length=1, max_length=255)
    secret_type: SecretType = SecretType.PASSWORD
    description: str | None = None
    requires_approval: bool = False
    exclusive_checkout: bool = True
    max_checkout_minutes: int = Field(60, ge=1, le=1440)
    # Optional initial secret; can also be set later with PUT /accounts/{id}/secret.
    secret: str | None = Field(None, min_length=1, max_length=16384)


class AccountUpdate(BaseModel):
    # Moving needs manage_accounts on both safes.
    safe_id: uuid.UUID | None = None
    description: str | None = None
    requires_approval: bool | None = None
    exclusive_checkout: bool | None = None
    max_checkout_minutes: int | None = Field(None, ge=1, le=1440)


class SecretSet(BaseModel):
    value: str = Field(min_length=1, max_length=16384)
