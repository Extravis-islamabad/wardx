"""Inventory service providers (targets and privileged accounts).

``build_*`` wire a service from a session for callers without a request (the
gateway, scheduler jobs); the ``get_*`` providers use the same wiring.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.dependencies.audit import build_audit_service
from src.dependencies.database import SQLSessionDep
from src.dependencies.vault import build_vault_service
from src.repositories.inventory.account_repository import AccountRepository
from src.repositories.inventory.target_repository import TargetRepository
from src.services.inventory.account_service import AccountService
from src.services.inventory.target_service import TargetService


def build_target_service(session: AsyncSession) -> TargetService:
    return TargetService(
        TargetRepository(session),
        AccountRepository(session),
        build_vault_service(session),
        build_audit_service(session),
    )


def build_account_service(session: AsyncSession) -> AccountService:
    return AccountService(
        AccountRepository(session),
        TargetRepository(session),
        build_vault_service(session),
        build_audit_service(session),
    )


async def get_target_service(session: SQLSessionDep) -> TargetService:
    return build_target_service(session)


async def get_account_service(session: SQLSessionDep) -> AccountService:
    return build_account_service(session)


TargetServiceDep = Annotated[TargetService, Depends(get_target_service)]
AccountServiceDep = Annotated[AccountService, Depends(get_account_service)]
