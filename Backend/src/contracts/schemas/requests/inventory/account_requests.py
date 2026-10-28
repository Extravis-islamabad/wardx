"""Account request shapes."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from src.core.enums import SecretType


class SnmpV2cIn(BaseModel):
    version: Literal["2c"]
    community: str = Field(min_length=1, max_length=255)


class SnmpV3In(BaseModel):
    """Fields not used by the security level must be left out (checked when stored)."""

    version: Literal["3"]
    security_name: str = Field(min_length=1, max_length=255)
    security_level: Literal["noAuthNoPriv", "authNoPriv", "authPriv"]
    auth_protocol: Literal["MD5", "SHA", "SHA-224", "SHA-256", "SHA-384", "SHA-512"] | None = None
    auth_password: str | None = Field(None, min_length=8, max_length=255)
    priv_protocol: Literal["DES", "3DES", "AES", "AES-192", "AES-256"] | None = None
    priv_password: str | None = Field(None, min_length=8, max_length=255)


SnmpSecretIn = Annotated[SnmpV2cIn | SnmpV3In, Field(discriminator="version")]


class AccountCreate(BaseModel):
    target_id: uuid.UUID
    # The safe the account goes into; omitted = the Default safe.
    safe_id: uuid.UUID | None = None
    username: str = Field(min_length=1, max_length=255)
    secret_type: SecretType = SecretType.PASSWORD
    description: str | None = None
    exclusive_checkout: bool = True
    max_checkout_minutes: int = Field(60, ge=1, le=1440)
    # Optional initial secret; can also be set later with PUT /accounts/{id}/secret.
    secret: str | None = Field(None, min_length=1, max_length=16384)
    # The initial secret of an snmp_v2c / snmp_v3 account (instead of ``secret``).
    snmp: SnmpSecretIn | None = None


class AccountUpdate(BaseModel):
    # Moving needs manage_accounts on both safes.
    safe_id: uuid.UUID | None = None
    description: str | None = None
    exclusive_checkout: bool | None = None
    max_checkout_minutes: int | None = Field(None, ge=1, le=1440)
    # Rotation overrides: they can only make the safe's policy stricter.
    rotate_after_use: bool | None = None
    rotation_interval_days: int | None = Field(None, ge=1, le=3650)
    password_length: int | None = Field(None, ge=12, le=128)
    reconcile_account_id: uuid.UUID | None = None


class SecretSet(BaseModel):
    # ``value`` for every type but SNMP; ``snmp`` for snmp_v2c / snmp_v3 accounts.
    value: str | None = Field(None, min_length=1, max_length=16384)
    snmp: SnmpSecretIn | None = None
