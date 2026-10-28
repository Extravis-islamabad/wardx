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
    created_at: datetime
    updated_at: datetime
    rotation_allowed: bool = False
    policy_overrides: dict[str, Any] = {}
    # Set when the target can never be rotated, e.g. "non-rotatable (Telnet)".
    non_rotatable_reason: str | None = None
