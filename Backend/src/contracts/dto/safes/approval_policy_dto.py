"""A safe's approval policy, and the snapshot a request runs under."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ApprovalLevelDTO:
    position: int
    required_approvals: int
    approver_type: str
    # user: the user's id; group: the normalised DN; None for safe_approvers.
    approver_key: str | None = None
    # For display only (user levels: full name, else username); never in a snapshot.
    approver_name: str | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "required_approvals": self.required_approvals,
            "approver_type": self.approver_type,
            "approver_key": self.approver_key,
        }


@dataclass(frozen=True)
class ApprovalPolicyDTO:
    safe_id: uuid.UUID
    approval_required: bool
    ticket_mode: str
    ticket_pattern: str | None
    approval_window_minutes: int
    approval_multi_use: bool
    level_timeout_hours: int
    levels: tuple[ApprovalLevelDTO, ...] = field(default_factory=tuple)

    def snapshot(self) -> dict[str, Any]:
        """What a request keeps: later policy edits never change a request in flight."""
        return {
            "levels": [lv.snapshot() for lv in self.levels],
            "approval_window_minutes": self.approval_window_minutes,
            "approval_multi_use": self.approval_multi_use,
            "level_timeout_hours": self.level_timeout_hours,
        }

    def audit_view(self) -> dict[str, Any]:
        return {
            "approval_required": self.approval_required,
            "ticket_mode": self.ticket_mode,
            "ticket_pattern": self.ticket_pattern,
            **self.snapshot(),
        }


@dataclass(frozen=True)
class RequestPolicyDTO:
    """The snapshot stored on a request (access.requests.policy)."""

    levels: tuple[ApprovalLevelDTO, ...]
    approval_window_minutes: int
    approval_multi_use: bool
    level_timeout_hours: int

    @classmethod
    def from_snapshot(cls, data: dict[str, Any] | None) -> RequestPolicyDTO:
        data = data or {}
        levels = tuple(
            ApprovalLevelDTO(
                position=int(lv["position"]),
                required_approvals=int(lv["required_approvals"]),
                approver_type=lv["approver_type"],
                approver_key=lv.get("approver_key"),
            )
            for lv in data.get("levels") or []
        )
        return cls(
            levels=levels,
            approval_window_minutes=int(data.get("approval_window_minutes", 120)),
            approval_multi_use=bool(data.get("approval_multi_use", False)),
            level_timeout_hours=int(data.get("level_timeout_hours", 24)),
        )

    def level(self, position: int) -> ApprovalLevelDTO | None:
        return next((lv for lv in self.levels if lv.position == position), None)

    @property
    def last_level(self) -> int:
        return max((lv.position for lv in self.levels), default=1)
