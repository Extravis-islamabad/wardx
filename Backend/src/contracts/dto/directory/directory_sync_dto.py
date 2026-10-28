"""Directory sync result DTO."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SyncResultDTO:
    """What a sync run found and did. Not frozen: the run fills it in as it goes."""

    status: str = "ok"  # ok | needs_review | failed
    dry_run: bool = False
    checked: int = 0
    disabled: list[dict[str, str]] = field(default_factory=list)
    enabled: list[str] = field(default_factory=list)
    role_changes: list[dict[str, str]] = field(default_factory=list)
    profile_updates: int = 0
    problems: list[str] = field(default_factory=list)
    revoked_checkouts: int = 0
    killed_sessions: int = 0

    def summary(self) -> dict[str, Any]:
        return self.__dict__.copy()
