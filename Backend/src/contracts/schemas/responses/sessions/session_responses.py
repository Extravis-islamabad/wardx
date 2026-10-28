"""Gateway session response shapes."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class SessionResponse(BaseModel):
    id: uuid.UUID
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
    has_recording: bool
    recording_sha256: str | None
    recording_bytes: int | None
    bytes_from_target: int
    commands_count: int
    blocked_count: int


class SessionCommandResponse(BaseModel):
    id: int
    occurred_at: datetime
    offset_seconds: float
    command: str
    verdict: str
    rule_id: uuid.UUID | None


class GatewayInfoResponse(BaseModel):
    host: str
    port: int
    login_format: str
