"""Command rule request shapes."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, field_validator, model_validator

from src.core.enums import Platform
from src.gateway.policy import MAX_PATTERN_LENGTH, compile_pattern


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


class CommandTest(BaseModel):
    command: str = Field(max_length=4000)
    account_id: uuid.UUID | None = None
