"""Rotation request shapes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RotationRequestIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class RotateIn(RotationRequestIn):
    # Connect and verify only; nothing on the device changes.
    dry_run: bool = False


class ResolveIn(BaseModel):
    action: Literal["keep_current", "use_candidate", "set_secret", "reconcile"]
    note: str = Field(min_length=3, max_length=500)
    # set_secret only: the password that is on the device now.
    secret: str | None = Field(None, min_length=1, max_length=16384)


class ConfirmIn(BaseModel):
    # At least 20 characters (checked by the service, with a clear message).
    reason: str = Field("", max_length=1000)


class MaintenanceWindowIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: list[int] = Field(min_length=1, max_length=7)
    start_hour: int = Field(0, ge=0, le=23)
    end_hour: int = Field(24, ge=1, le=24)


class SafeRotationPolicyIn(BaseModel):
    rotate_after_use: bool = False
    rotation_interval_days: int | None = Field(None, ge=1, le=3650)
    verify_interval_hours: int = Field(24, ge=1, le=8760)
    auto_reconcile: bool = False
    maintenance_window: MaintenanceWindowIn | None = None
    max_release_wait_minutes: int = Field(240, ge=5, le=10080)
