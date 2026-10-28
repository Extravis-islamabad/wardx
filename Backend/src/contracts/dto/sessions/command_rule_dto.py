"""Command rule DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CommandRuleDTO:
    id: uuid.UUID
    pattern: str
    description: str | None
    account_id: uuid.UUID | None
    target_id: uuid.UUID | None
    platform: str | None
    is_active: bool
    created_at: datetime


@dataclass(frozen=True)
class RuleScopeDTO:
    """Where a command runs: rules scoped to this account, its target, its platform or
    nothing apply."""

    account_id: uuid.UUID
    target_id: uuid.UUID
    platform: str


@dataclass(frozen=True)
class CommandTestResultDTO:
    blocked: bool
    rule_id: uuid.UUID | None
    description: str | None
