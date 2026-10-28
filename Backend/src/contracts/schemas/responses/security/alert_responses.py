"""Security alert response shapes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AlertResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    severity: str
    kind: str
    message: str
    actor_id: uuid.UUID | None
    actor_name: str | None
    object_type: str | None
    object_id: uuid.UUID | None
    details: dict[str, Any]
    acknowledged_by: uuid.UUID | None
    acknowledged_at: datetime | None
