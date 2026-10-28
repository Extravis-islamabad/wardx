"""Safe service providers.

``build_*`` wire a service from a session for callers without a request (the
gateway, scheduler jobs); the ``get_*`` providers use the same wiring.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.tenant import current_tenant
from src.dependencies.audit import build_audit_service
from src.dependencies.database import SQLSessionDep
from src.dependencies.directory import build_directory_service
from src.dependencies.identity import build_user_grant_service
from src.repositories.directory.directory_config_repository import DirectoryConfigRepository
from src.repositories.identity.group_cache_repository import GroupCacheRepository
from src.repositories.identity.user_repository import UserRepository
from src.repositories.safes.safe_health_repository import SafeHealthRepository
from src.repositories.safes.safe_member_repository import SafeMemberRepository
from src.repositories.safes.safe_repository import SafeRepository
from src.services.directory.group_membership_service import GroupMembershipService
from src.services.safes.safe_access_service import SafeAccessService
from src.services.safes.safe_health_service import SafeHealthService
from src.services.safes.safe_service import SafeService


def build_group_membership_service(session: AsyncSession) -> GroupMembershipService:
    return GroupMembershipService(
        GroupCacheRepository(session),
        UserRepository(session),
        build_directory_service(session),
        get_settings(),
        side_sessions=current_tenant().session_factory(),
    )


def build_safe_access_service(session: AsyncSession) -> SafeAccessService:
    return SafeAccessService(
        SafeMemberRepository(session),
        SafeRepository(session),
        build_group_membership_service(session),
    )


def build_safe_service(session: AsyncSession) -> SafeService:
    return SafeService(
        SafeRepository(session),
        SafeMemberRepository(session),
        UserRepository(session),
        build_safe_access_service(session),
        build_audit_service(session),
    )


def build_safe_health_service(session: AsyncSession) -> SafeHealthService:
    return SafeHealthService(
        SafeHealthRepository(session),
        DirectoryConfigRepository(session),
        build_user_grant_service(session),
    )


async def get_safe_health_service(session: SQLSessionDep) -> SafeHealthService:
    return build_safe_health_service(session)


async def get_safe_service(session: SQLSessionDep) -> SafeService:
    return build_safe_service(session)


SafeServiceDep = Annotated[SafeService, Depends(get_safe_service)]
SafeHealthServiceDep = Annotated[SafeHealthService, Depends(get_safe_health_service)]
