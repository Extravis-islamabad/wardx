"""Tenant key DTOs. Carry the wrapped form only; plaintext keys never leave the service."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class TenantKeyDTO:
    id: uuid.UUID
    tenant_id: uuid.UUID
    purpose: str
    version: int
    state: str
    kek_id: str
    wrapped_key: bytes | None
    wrap_nonce: bytes | None
