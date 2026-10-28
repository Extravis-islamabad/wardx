"""Rotation service providers.

``build_*`` wire a service from a session for callers without a request (the
scheduler, the gateway); the ``get_*`` providers use the same wiring.
"""

from __future__ import annotations

import socket
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.tenant import current_tenant
from src.dependencies.audit import build_audit_service
from src.dependencies.database import SQLSessionDep
from src.dependencies.identity import build_alert_service
from src.dependencies.inventory import build_account_service
from src.dependencies.sessions import build_host_key_service, build_tls_cert_service
from src.dependencies.vault import build_vault_service
from src.repositories.rotation.rotation_account_repository import RotationAccountRepository
from src.repositories.rotation.rotation_job_repository import RotationJobRepository
from src.repositories.security.alert_repository import AlertRepository
from src.rotation.drivers.registry import DriverRegistry, default_registry
from src.services.rotation.rotation_engine import Checkpoint, RotationEngine
from src.services.rotation.rotation_guard import RotationGuard
from src.services.rotation.rotation_review_service import RotationReviewService
from src.services.rotation.rotation_scheduler_service import RotationSchedulerService
from src.services.rotation.rotation_service import RotationService
from src.services.rotation.rotation_store import RotationStore
from src.services.rotation.rotation_worker import RotationWorker
from src.services.rotation.safe_rotation_policy_service import SafeRotationPolicyService


def build_rotation_guard(session: AsyncSession) -> RotationGuard:
    return RotationGuard(
        RotationJobRepository(session),
        RotationAccountRepository(session),
        build_audit_service(session),
    )


def build_rotation_store(session: AsyncSession) -> RotationStore:
    return RotationStore(
        RotationJobRepository(session),
        RotationAccountRepository(session),
        build_vault_service(session),
        build_audit_service(session),
        build_alert_service(session),
        host_keys=build_host_key_service(session),
        tls_certs=build_tls_cert_service(session),
        lease_seconds=get_settings().rotation_lease_seconds,
    )


def build_rotation_scheduler_service(session: AsyncSession) -> RotationSchedulerService:
    return RotationSchedulerService(
        RotationJobRepository(session),
        RotationAccountRepository(session),
        build_vault_service(session),
        build_audit_service(session),
        build_alert_service(session),
    )


def build_rotation_engine(
    settings: Settings,
    *,
    registry: DriverRegistry | None = None,
    checkpoint: Checkpoint | None = None,
) -> RotationEngine:
    return RotationEngine(
        current_tenant().session_factory(),
        build_rotation_store,
        registry or default_registry(),
        enabled=settings.rotation_enabled,
        dry_run=settings.rotation_dry_run,
        connect_timeout=settings.rotation_connect_timeout_seconds,
        command_timeout=settings.rotation_command_timeout_seconds,
        checkpoint=checkpoint,
    )


def build_rotation_worker(
    settings: Settings,
    *,
    registry: DriverRegistry | None = None,
    checkpoint: Checkpoint | None = None,
) -> RotationWorker:
    return RotationWorker(
        current_tenant().session_factory(),
        build_rotation_engine(settings, registry=registry, checkpoint=checkpoint),
        worker_id=f"{socket.gethostname()}:{id(settings)}"[:100],
        pool_size=settings.rotation_workers,
        lease_seconds=settings.rotation_lease_seconds,
    )


def build_rotation_service(session: AsyncSession) -> RotationService:
    return RotationService(
        RotationJobRepository(session),
        RotationAccountRepository(session),
        build_account_service(session),
        build_audit_service(session),
        get_settings(),
    )


def build_rotation_review_service(session: AsyncSession) -> RotationReviewService:
    return RotationReviewService(
        RotationJobRepository(session),
        RotationAccountRepository(session),
        build_account_service(session),
        build_vault_service(session),
        AlertRepository(session),
        build_audit_service(session),
    )


def build_safe_rotation_policy_service(session: AsyncSession) -> SafeRotationPolicyService:
    from src.dependencies.safes import build_safe_access_service

    return SafeRotationPolicyService(
        RotationAccountRepository(session),
        build_safe_access_service(session),
        build_audit_service(session),
    )


async def get_rotation_service(session: SQLSessionDep) -> RotationService:
    return build_rotation_service(session)


async def get_rotation_review_service(session: SQLSessionDep) -> RotationReviewService:
    return build_rotation_review_service(session)


async def get_safe_rotation_policy_service(session: SQLSessionDep) -> SafeRotationPolicyService:
    return build_safe_rotation_policy_service(session)


RotationServiceDep = Annotated[RotationService, Depends(get_rotation_service)]
RotationReviewServiceDep = Annotated[RotationReviewService, Depends(get_rotation_review_service)]
SafeRotationPolicyServiceDep = Annotated[
    SafeRotationPolicyService, Depends(get_safe_rotation_policy_service)
]
