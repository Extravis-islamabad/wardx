"""Safe service providers.

``build_*`` wire a service from a session for callers without a request (the
gateway, scheduler jobs); the ``get_*`` providers use the same wiring.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.dependencies.audit import build_audit_service
from src.dependencies.database import SQLSessionDep
from src.repositories.identity.user_repository import UserRepository
from src.repositories.safes.safe_member_repository import SafeMemberRepository
from src.repositories.safes.safe_repository import SafeRepository
from src.services.safes.safe_access_service import SafeAccessService
from src.services.safes.safe_service import SafeService


def build_safe_access_service(session: AsyncSession) -> SafeAccessService:
    return SafeAccessService(SafeMemberRepository(session), SafeRepository(session))


def build_safe_service(session: AsyncSession) -> SafeService:
    return SafeService(
        SafeRepository(session),
        SafeMemberRepository(session),
        UserRepository(session),
        build_safe_access_service(session),
        build_audit_service(session),
    )


async def get_safe_service(session: SQLSessionDep) -> SafeService:
    return build_safe_service(session)


SafeServiceDep = Annotated[SafeService, Depends(get_safe_service)]
