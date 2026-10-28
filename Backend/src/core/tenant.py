"""The current tenant: the one seam new modules take their DB session and keys from.

WardX is single-tenant until the tenancy step (Backend/TENANCY_KEYS.md), so
``current_tenant`` always returns the default tenant and its session factory is
the one database. When tenancy lands, only this module and the request
dependency that picks the tenant change; modules keep asking the context.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.db import session_factory

# Fixed, so the default tenant's rows (keys, later everything) keep their id
# when it becomes the first real tenant.
DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@dataclass(frozen=True)
class TenantContext:
    tenant_id: uuid.UUID
    slug: str

    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return session_factory()


DEFAULT_TENANT = TenantContext(tenant_id=DEFAULT_TENANT_ID, slug="default")


def current_tenant() -> TenantContext:
    return DEFAULT_TENANT
