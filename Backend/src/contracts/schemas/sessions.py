"""Gateway session and command-rule schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core.enums import Platform
from src.gateway.policy import MAX_PATTERN_LENGTH, compile_pattern


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class SessionCommandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    offset_seconds: float
    command: str
    verdict: str
    rule_id: uuid.UUID | None


class CommandRuleCreate(BaseModel):
    pattern: str = Field(min_length=1, max_length=MAX_PATTERN_LENGTH)
    description: str | None = Field(None, max_length=500)
    account_id: uuid.UUID | None = None
    target_id: uuid.UUID | None = None
    platform: Platform | None = None

    @field_validator("pattern")
    @classmethod
    def _valid_regex(cls, value: str) -> str:
        compile_pattern(value)
        return value

    @model_validator(mode="after")
    def _one_scope(self) -> CommandRuleCreate:
        if sum(x is not None for x in (self.account_id, self.target_id, self.platform)) > 1:
            raise ValueError("scope a rule to one account, one target or one platform (or none)")
        return self


class CommandRuleUpdate(BaseModel):
    pattern: str | None = Field(None, min_length=1, max_length=MAX_PATTERN_LENGTH)
    description: str | None = Field(None, max_length=500)
    is_active: bool | None = None

    @field_validator("pattern")
    @classmethod
    def _valid_regex(cls, value: str | None) -> str | None:
        if value is not None:
            compile_pattern(value)
        return value


class CommandRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pattern: str
    description: str | None
    account_id: uuid.UUID | None
    target_id: uuid.UUID | None
    platform: str | None
    is_active: bool
    created_at: datetime


class CommandTest(BaseModel):
    command: str = Field(max_length=4000)
    account_id: uuid.UUID | None = None


class CommandTestResult(BaseModel):
    blocked: bool
    rule_id: uuid.UUID | None
    description: str | None


class GatewayInfo(BaseModel):
    host: str
    port: int
    login_format: str
