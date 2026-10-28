"""Access service providers (requests and check-outs).

``build_*`` wire a service from a session for callers without a request (the
gateway, scheduler jobs); the ``get_*`` providers use the same wiring.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.dependencies.audit import build_audit_service
from src.dependencies.database import SQLSessionDep
from src.dependencies.inventory import build_account_service
from src.dependencies.vault import build_vault_service
from src.repositories.access.access_request_repository import AccessRequestRepository
from src.repositories.access.checkout_repository import CheckoutRepository
from src.repositories.inventory.account_repository import AccountRepository
from src.services.access.access_request_service import AccessRequestService
from src.services.access.checkout_service import CheckoutService


def build_access_request_service(session: AsyncSession) -> AccessRequestService:
    return AccessRequestService(
        AccessRequestRepository(session),
        AccountRepository(session),
        build_audit_service(session),
        get_settings(),
    )


def build_checkout_service(session: AsyncSession) -> CheckoutService:
    return CheckoutService(
        CheckoutRepository(session),
        AccessRequestRepository(session),
        build_account_service(session),
        build_vault_service(session),
        build_audit_service(session),
    )


async def get_access_request_service(session: SQLSessionDep) -> AccessRequestService:
    return build_access_request_service(session)


async def get_checkout_service(session: SQLSessionDep) -> CheckoutService:
    return build_checkout_service(session)


AccessRequestServiceDep = Annotated[AccessRequestService, Depends(get_access_request_service)]
CheckoutServiceDep = Annotated[CheckoutService, Depends(get_checkout_service)]
