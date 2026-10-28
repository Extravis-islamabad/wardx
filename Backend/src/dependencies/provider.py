"""Credential provider providers: app management, app authentication, credential fetch.

``get_current_app`` is the provider routes' gate. It carries the ``provider.fetch``
codename for the route-coverage security test, like ``require_permission`` does, and
accepts only application tokens: user tokens are refused, and app tokens are refused
everywhere else (``get_current_user`` cannot verify them).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.dto.provider.app_dto import AppPrincipalDTO
from src.core.client_ip import source_ip
from src.core.config import get_settings
from src.core.permissions import PROVIDER_FETCH
from src.core.tenant import current_tenant
from src.dependencies.audit import build_audit_service
from src.dependencies.database import SQLSessionDep
from src.dependencies.vault import build_vault_service
from src.repositories.provider.app_repository import AppRepository
from src.repositories.provider.credential_repository import CredentialRepository
from src.services.provider.app_auth_service import AppAuthService
from src.services.provider.app_service import AppService
from src.services.provider.credential_service import CredentialService
from src.services.provider.rate_limit_service import RateLimitService

_bearer = HTTPBearer(auto_error=False)


def build_rate_limit_service() -> RateLimitService:
    return RateLimitService(current_tenant().session_factory())


def build_app_service(session: AsyncSession) -> AppService:
    return AppService(AppRepository(session), build_audit_service(session))


def build_app_auth_service(session: AsyncSession) -> AppAuthService:
    return AppAuthService(
        AppRepository(session),
        build_audit_service(session),
        build_rate_limit_service(),
        get_settings(),
    )


def build_credential_service(session: AsyncSession) -> CredentialService:
    return CredentialService(
        CredentialRepository(session),
        build_vault_service(session),
        build_audit_service(session),
        build_rate_limit_service(),
    )


async def get_app_service(session: SQLSessionDep) -> AppService:
    return build_app_service(session)


async def get_app_auth_service(session: SQLSessionDep) -> AppAuthService:
    return build_app_auth_service(session)


async def get_credential_service(session: SQLSessionDep) -> CredentialService:
    return build_credential_service(session)


AppServiceDep = Annotated[AppService, Depends(get_app_service)]
AppAuthServiceDep = Annotated[AppAuthService, Depends(get_app_auth_service)]
CredentialServiceDep = Annotated[CredentialService, Depends(get_credential_service)]


def provider_source_ip(request: Request) -> str | None:
    """The caller's address: the connection, or X-Forwarded-For via trusted proxies only."""
    return source_ip(request, get_settings().trusted_proxies)


async def get_current_app(
    request: Request,
    auth: AppAuthServiceDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AppPrincipalDTO:
    token = credentials.credentials if credentials else None
    return await auth.authenticate(token, provider_source_ip(request))


# Read by the route-coverage security test: the codename this gate enforces.
get_current_app.permission_codenames = (PROVIDER_FETCH,)  # type: ignore[attr-defined]

AppPrincipalDep = Annotated[AppPrincipalDTO, Depends(get_current_app)]
