"""Application identity and credential provider response shapes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AppSecretResponse(BaseModel):
    id: uuid.UUID
    slot: int
    # The first characters of the secret, to tell secrets apart; never the secret.
    prefix: str
    # active | expired | revoked
    status: str
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class AppResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    client_id: str
    enabled: bool
    ip_allowlist: list[str]
    rate_limit_per_minute: int
    # Enabled, at least one allowed network and an active secret: it can get a token.
    usable: bool
    secrets: list[AppSecretResponse]
    created_at: datetime
    updated_at: datetime


class NewAppSecretResponse(BaseModel):
    """Shown once: WardX stores only a hash of client_secret and can never show it again."""

    app: AppResponse
    secret_id: uuid.UUID
    client_id: str
    client_secret: str


class AppFetchEventResponse(BaseModel):
    occurred_at: datetime
    outcome: str
    source_ip: str | None
    kind: str | None
    purpose: str | None
    account_id: str | None
    target_id: str | None
    username: str | None
    version_id: str | None
    error_code: str | None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = Field(description="Seconds the token stays valid (300)")


class CredentialTargetResponse(BaseModel):
    id: uuid.UUID
    name: str
    address: str
    external_ref: str | None


class CredentialResponse(BaseModel):
    account_id: uuid.UUID
    target: CredentialTargetResponse
    kind: str
    username: str
    # ssh: {password} or {private_key}; enable: {password}; api: {token};
    # snmp: {version: "2c", community} or {version: "3", security_name, security_level, ...}
    secret: dict[str, Any]
    version_id: str
    max_cache_seconds: int
    issued_at: datetime
