"""Directory (LDAP / Active Directory) service providers.

``build_*`` wire a service from a session for callers without a request (the
gateway, scheduler jobs); the ``get_*`` providers use the same wiring.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.tenant import current_tenant
from src.dependencies.audit import build_audit_service
from src.dependencies.database import SQLSessionDep
from src.dependencies.vault import build_vault_service
from src.repositories.access.checkout_repository import CheckoutRepository
from src.repositories.directory.directory_config_repository import DirectoryConfigRepository
from src.repositories.identity.group_cache_repository import GroupCacheRepository
from src.repositories.identity.user_repository import UserRepository
from src.repositories.rotation.rotation_account_repository import RotationAccountRepository
from src.repositories.rotation.rotation_job_repository import RotationJobRepository
from src.repositories.sessions.gateway_session_repository import GatewaySessionRepository
from src.services.directory.directory_service import DirectoryService
from src.services.directory.directory_sync_service import DirectorySyncService
from src.services.rotation.rotation_guard import RotationGuard


def build_directory_service(session: AsyncSession) -> DirectoryService:
    return DirectoryService(
        DirectoryConfigRepository(session),
        UserRepository(session),
        build_vault_service(session),
        build_audit_service(session),
        side_sessions=current_tenant().session_factory(),
    )


def build_directory_sync_service(session: AsyncSession) -> DirectorySyncService:
    return DirectorySyncService(
        build_directory_service(session),
        DirectoryConfigRepository(session),
        UserRepository(session),
        CheckoutRepository(session),
        GatewaySessionRepository(session),
        build_audit_service(session),
        GroupCacheRepository(session),
        RotationGuard(
            RotationJobRepository(session),
            RotationAccountRepository(session),
            build_audit_service(session),
        ),
    )


async def get_directory_service(session: SQLSessionDep) -> DirectoryService:
    return build_directory_service(session)


async def get_directory_sync_service(session: SQLSessionDep) -> DirectorySyncService:
    return build_directory_sync_service(session)


DirectoryServiceDep = Annotated[DirectoryService, Depends(get_directory_service)]
DirectorySyncServiceDep = Annotated[DirectorySyncService, Depends(get_directory_sync_service)]
