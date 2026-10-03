from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from src.contracts.schemas.common import APIResponse, ok
from src.dependencies.auth import SessionDep
from src.services import vault_service

router = APIRouter(tags=["health"])


@router.get("/health/ready", response_model=APIResponse[dict])
async def ready(session: SessionDep):
    await session.execute(text("SELECT 1"))
    vault_service.keyring()  # raises when the vault is sealed
    return ok({"database": "ok", "vault": "unsealed"})
