"""Application identity DTOs (docs/phase1/CREDENTIAL_PROVIDER.md §1, §2)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AppSecretDTO:
    id: uuid.UUID
    app_id: uuid.UUID
    slot: int
    prefix: str
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime

    def is_active(self, now: datetime) -> bool:
        """Unrevoked and unexpired: the only secrets a token can be issued for."""
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > now)


@dataclass(frozen=True)
class AppSecretHashDTO:
    """A secret's hash, for verification only; never leaves the auth service."""

    id: uuid.UUID
    secret_hash: str
    expires_at: datetime | None


@dataclass(frozen=True)
class AppDTO:
    id: uuid.UUID
    name: str
    description: str | None
    client_id: str
    enabled: bool
    ip_allowlist: tuple[str, ...]
    rate_limit_per_minute: int
    token_version: int
    created_at: datetime
    updated_at: datetime
    secrets: tuple[AppSecretDTO, ...] = ()

    def audit_view(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "ip_allowlist": list(self.ip_allowlist),
            "rate_limit_per_minute": self.rate_limit_per_minute,
        }


@dataclass(frozen=True)
class NewAppSecretDTO:
    """A secret just created: the plaintext is returned once and never stored."""

    app: AppDTO
    secret: AppSecretDTO
    client_secret: str


@dataclass(frozen=True)
class AppTokenDTO:
    access_token: str
    expires_in: int


@dataclass(frozen=True)
class AppPrincipalDTO:
    """An authenticated application identity on a provider request."""

    id: uuid.UUID
    name: str
    rate_limit_per_minute: int
    source_ip: str | None
