"""Identity service providers (sign-in, MFA, user administration).

``build_*`` wire a service from a session for callers without a request (the
gateway, startup); the ``get_*`` providers use the same wiring.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.dependencies.audit import build_audit_service
from src.dependencies.database import SQLSessionDep
from src.dependencies.directory import build_directory_service
from src.dependencies.vault import build_vault_service
from src.repositories.identity.mfa_repository import MfaRepository
from src.repositories.identity.user_repository import UserRepository
from src.services.identity.auth_service import AuthService
from src.services.identity.mfa_service import MfaService
from src.services.identity.user_service import UserService


def build_user_service(session: AsyncSession) -> UserService:
    return UserService(UserRepository(session), build_audit_service(session))


def build_mfa_service(session: AsyncSession) -> MfaService:
    return MfaService(
        MfaRepository(session),
        UserRepository(session),
        build_vault_service(session),
        build_audit_service(session),
        get_settings(),
    )


def build_auth_service(session: AsyncSession) -> AuthService:
    return AuthService(
        UserRepository(session),
        build_mfa_service(session),
        build_directory_service(session),
        build_audit_service(session),
        get_settings(),
    )


async def get_user_service(session: SQLSessionDep) -> UserService:
    return build_user_service(session)


async def get_mfa_service(session: SQLSessionDep) -> MfaService:
    return build_mfa_service(session)


async def get_auth_service(session: SQLSessionDep) -> AuthService:
    return build_auth_service(session)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
MfaServiceDep = Annotated[MfaService, Depends(get_mfa_service)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
