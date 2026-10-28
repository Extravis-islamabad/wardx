"""Health router.

GET /health/ready   — readiness: database reachable and vault unsealed
"""

from __future__ import annotations

from fastapi import APIRouter

from src.contracts.schemas.responses.common import APIResponse, ok
from src.dependencies.health import HealthServiceDep

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/ready", response_model=APIResponse[dict], summary="Readiness probe")
async def ready(service: HealthServiceDep) -> APIResponse[dict]:
    return ok(await service.readiness())
