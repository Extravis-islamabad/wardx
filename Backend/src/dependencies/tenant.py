"""The request's tenant. Always the default tenant until the tenancy step."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from src.core.tenant import TenantContext, current_tenant


async def get_tenant() -> TenantContext:
    return current_tenant()


TenantDep = Annotated[TenantContext, Depends(get_tenant)]
