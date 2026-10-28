"""Host-key probe DTO: what a target presents now, next to what is pinned."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class HostKeyProbeDTO:
    target_id: uuid.UUID
    presented_fingerprint: str
    key_type: str
    pinned_fingerprint: str | None
    matches_pin: bool
    mismatch_at: datetime | None
    mismatch_fingerprint: str | None


@dataclass(frozen=True)
class TlsCertProbeDTO:
    """The API-SSL certificate a target presents now, next to the pinned one."""

    target_id: uuid.UUID
    presented_fingerprint: str
    subject: str
    not_after: datetime | None
    pinned_fingerprint: str | None
    matches_pin: bool
    mismatch_at: datetime | None
    mismatch_fingerprint: str | None
