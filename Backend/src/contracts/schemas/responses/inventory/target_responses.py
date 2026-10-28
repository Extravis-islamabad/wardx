"""Target response shapes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TargetResponse(BaseModel):
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
    ssh_host_key_fingerprint: str | None = None
    ssh_host_key_learned_at: datetime | None = None
    host_key_mismatch_at: datetime | None = None
    host_key_mismatch_fingerprint: str | None = None
    # MikroTik API-SSL: port (None = 8729), TLS or cleartext-only, and the pinned
    # certificate's SHA-256 fingerprint (ROTATION.md §15).
    api_port: int | None = None
    api_tls: bool = True
    tls_cert_fingerprint: str | None = None
    tls_cert_learned_at: datetime | None = None
    tls_cert_mismatch_at: datetime | None = None
    tls_cert_mismatch_fingerprint: str | None = None
    created_at: datetime
    updated_at: datetime
    rotation_allowed: bool = False
    policy_overrides: dict[str, Any] = {}
    # Set when the target can never be rotated, e.g. "non-rotatable (Telnet)".
    non_rotatable_reason: str | None = None
