"""Tenant key service provider."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.tenant import TenantContext, current_tenant
from src.keys.runtime import key_provider
from src.repositories.keys.tenant_key_repository import TenantKeyRepository
from src.services.keys.tenant_key_service import TenantKeyService


def build_tenant_key_service(
    session: AsyncSession, tenant: TenantContext | None = None
) -> TenantKeyService:
    return TenantKeyService(
        TenantKeyRepository(session), key_provider(), tenant or current_tenant()
    )
