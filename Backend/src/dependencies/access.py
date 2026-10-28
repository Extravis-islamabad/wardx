"""Access service providers (requests and check-outs).

``build_*`` wire a service from a session for callers without a request (the
gateway, scheduler jobs); the ``get_*`` providers use the same wiring.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.dependencies.audit import build_audit_service
from src.dependencies.database import SQLSessionDep
from src.dependencies.identity import build_alert_service
from src.dependencies.inventory import build_account_service
from src.dependencies.rotation import build_rotation_guard
from src.dependencies.safes import build_approval_policy_service, build_safe_access_service
from src.dependencies.vault import build_vault_service
from src.repositories.access.access_request_repository import AccessRequestRepository
from src.repositories.access.checkout_repository import CheckoutRepository
from src.repositories.identity.mfa_repository import MfaRepository
from src.repositories.identity.user_repository import UserRepository
from src.repositories.inventory.account_repository import AccountRepository
from src.repositories.notify.notification_repository import NotificationRepository
from src.repositories.safes.approval_policy_repository import ApprovalPolicyRepository
from src.services.access.access_request_service import AccessRequestService
from src.services.access.approver_service import ApproverService
from src.services.access.checkout_service import CheckoutService
from src.services.access.emergency_service import EmergencyAccessService
from src.services.access.ticket_validator import RegexTicketValidator, TicketValidator
from src.services.notify.notification_service import NotificationService


def build_notification_service(session: AsyncSession) -> NotificationService:
    return NotificationService(NotificationRepository(session))


def build_ticket_validator() -> TicketValidator:
    """Format-only today; a SupportX-backed validator plugs in here."""
    return RegexTicketValidator()


def build_access_request_service(session: AsyncSession) -> AccessRequestService:
    access = build_safe_access_service(session)
    return AccessRequestService(
        AccessRequestRepository(session),
        AccountRepository(session),
        build_audit_service(session),
        access,
        build_approval_policy_service(session),
        ApproverService(access, ApprovalPolicyRepository(session)),
        build_notification_service(session),
        build_ticket_validator(),
    )


def build_checkout_service(session: AsyncSession) -> CheckoutService:
    return CheckoutService(
        CheckoutRepository(session),
        AccessRequestRepository(session),
        build_account_service(session),
        build_vault_service(session),
        build_audit_service(session),
        build_notification_service(session),
        build_rotation_guard(session),
    )


async def get_access_request_service(session: SQLSessionDep) -> AccessRequestService:
    return build_access_request_service(session)


async def get_checkout_service(session: SQLSessionDep) -> CheckoutService:
    return build_checkout_service(session)


AccessRequestServiceDep = Annotated[AccessRequestService, Depends(get_access_request_service)]
CheckoutServiceDep = Annotated[CheckoutService, Depends(get_checkout_service)]


def build_emergency_access_service(session: AsyncSession) -> EmergencyAccessService:
    return EmergencyAccessService(
        build_account_service(session),
        CheckoutRepository(session),
        UserRepository(session),
        MfaRepository(session),
        build_vault_service(session),
        build_alert_service(session),
        build_audit_service(session),
        build_rotation_guard(session),
    )


async def get_emergency_access_service(session: SQLSessionDep) -> EmergencyAccessService:
    return build_emergency_access_service(session)


EmergencyAccessServiceDep = Annotated[EmergencyAccessService, Depends(get_emergency_access_service)]


async def get_notification_service(session: SQLSessionDep) -> NotificationService:
    return build_notification_service(session)


NotificationServiceDep = Annotated[NotificationService, Depends(get_notification_service)]
