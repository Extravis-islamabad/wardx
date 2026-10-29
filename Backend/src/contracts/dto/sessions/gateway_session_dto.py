"""Gateway session DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class GatewaySessionDTO:
    id: uuid.UUID
    checkout_id: uuid.UUID | None
    user_id: uuid.UUID
    username: str
    account_id: uuid.UUID | None
    account_username: str
    target_id: uuid.UUID | None
    target_name: str
    target_address: str
    protocol: str
    mode: str
    exec_command: str | None
    client_ip: str | None
    gateway_node: str | None
    status: str
    started_at: datetime
    ended_at: datetime | None
    close_reason: str | None
    terminate_requested_at: datetime | None
    recording_path: str | None
    recording_sha256: str | None
    recording_bytes: int | None
    bytes_from_target: int
    commands_count: int
    blocked_count: int
    recording_key: str | None = None
    recording_encrypted: bool = False
    recording_incomplete: bool = False
    recording_ciphertext_sha256: str | None = None
    recording_migrated_at: datetime | None = None
    recording_original_removed_at: datetime | None = None

    @property
    def has_recording(self) -> bool:
        return self.recording_key is not None or self.recording_path is not None


@dataclass(frozen=True)
class GatewaySessionFilterDTO:
    # Only this user's sessions; None means every session.
    user_id: uuid.UUID | None = None
    status: str | None = None
    search: str | None = None


@dataclass(frozen=True)
class SessionCommandDTO:
    id: int
    occurred_at: datetime
    offset_seconds: float
    command: str
    verdict: str
    rule_id: uuid.UUID | None
