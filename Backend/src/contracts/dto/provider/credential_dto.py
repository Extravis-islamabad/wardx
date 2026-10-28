"""Credential provider DTOs: what a fetch asks for and what it returns (§4)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class FetchQueryDTO:
    """A fetch by target: exactly one of external_ref, address or name is set."""

    kind: str
    purpose: str
    external_ref: str | None = None
    address: str | None = None
    name: str | None = None
    username: str | None = None

    @property
    def match_by(self) -> str:
        return "external_ref" if self.external_ref else "address" if self.address else "name"


@dataclass(frozen=True)
class FetchCandidateDTO:
    """An account the app may fetch: its safe's settings and its serving state."""

    account_id: uuid.UUID
    username: str
    secret_type: str
    secret_version: int
    risk_flags: tuple[str, ...]
    sync_status: str
    rotation_status: str
    target_id: uuid.UUID
    target_name: str
    target_address: str
    target_external_ref: str | None
    safe_id: uuid.UUID
    approval_required: bool
    allow_app_fetch: bool
    app_cache_seconds: int


@dataclass(frozen=True)
class FetchedCredentialDTO:
    candidate: FetchCandidateDTO
    kind: str
    secret: dict[str, Any]
    version_id: str
    max_cache_seconds: int
    issued_at: datetime
