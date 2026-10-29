"""Gateway session, command rule and host key service providers.

``build_*`` wire a service from a session for callers without a request (the
gateway, scheduler jobs); the ``get_*`` providers use the same wiring.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.dependencies.audit import build_audit_service
from src.dependencies.database import SQLSessionDep
from src.dependencies.keys import build_tenant_key_service
from src.repositories.inventory.account_repository import AccountRepository
from src.repositories.inventory.target_repository import TargetRepository
from src.repositories.sessions.command_rule_repository import CommandRuleRepository
from src.repositories.sessions.gateway_node_repository import GatewayNodeRepository
from src.repositories.sessions.gateway_session_repository import GatewaySessionRepository
from src.services.session_recordings.recording_migration_service import (
    RecordingMigrationService,
)
from src.services.sessions.command_rule_service import CommandRuleService
from src.services.sessions.gateway_node_service import GatewayNodeService
from src.services.sessions.gateway_session_service import GatewaySessionService
from src.services.sessions.host_key_service import HostKeyService
from src.services.sessions.session_service import SessionService
from src.services.sessions.tls_cert_service import TlsCertService
from src.storage.object_store import ObjectStore, build_object_store


def build_session_service(session: AsyncSession) -> SessionService:
    return SessionService(
        GatewaySessionRepository(session),
        build_audit_service(session),
        Path(get_settings().recording_dir),
        recording_store(),
        build_tenant_key_service(session),
    )


def build_recording_migration_service(session: AsyncSession) -> RecordingMigrationService:
    return RecordingMigrationService(
        GatewaySessionRepository(session),
        build_audit_service(session),
        build_tenant_key_service(session),
        recording_store(),
        Path(get_settings().recording_dir),
    )


@lru_cache
def recording_store() -> ObjectStore:
    """One object store client per process."""
    return build_object_store(get_settings())


def build_command_rule_service(session: AsyncSession) -> CommandRuleService:
    return CommandRuleService(
        CommandRuleRepository(session),
        AccountRepository(session),
        TargetRepository(session),
        build_audit_service(session),
    )


def build_gateway_session_service(session: AsyncSession) -> GatewaySessionService:
    return GatewaySessionService(GatewaySessionRepository(session), build_audit_service(session))


def build_gateway_node_service(session: AsyncSession) -> GatewayNodeService:
    from src.dependencies.access import build_checkout_service

    return GatewayNodeService(
        GatewayNodeRepository(session),
        GatewaySessionRepository(session),
        build_checkout_service(session),
        build_audit_service(session),
    )


def build_host_key_service(session: AsyncSession) -> HostKeyService:
    from src.dependencies.identity import build_alert_service
    from src.dependencies.safes import build_safe_access_service

    return HostKeyService(
        TargetRepository(session),
        AccountRepository(session),
        build_safe_access_service(session),
        build_alert_service(session),
        build_audit_service(session),
    )


def build_tls_cert_service(session: AsyncSession) -> TlsCertService:
    from src.dependencies.identity import build_alert_service
    from src.dependencies.safes import build_safe_access_service

    return TlsCertService(
        TargetRepository(session),
        AccountRepository(session),
        build_safe_access_service(session),
        build_alert_service(session),
        build_audit_service(session),
    )


async def get_session_service(session: SQLSessionDep) -> SessionService:
    return build_session_service(session)


async def get_command_rule_service(session: SQLSessionDep) -> CommandRuleService:
    return build_command_rule_service(session)


async def get_host_key_service(session: SQLSessionDep) -> HostKeyService:
    return build_host_key_service(session)


async def get_tls_cert_service(session: SQLSessionDep) -> TlsCertService:
    return build_tls_cert_service(session)


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
CommandRuleServiceDep = Annotated[CommandRuleService, Depends(get_command_rule_service)]
HostKeyServiceDep = Annotated[HostKeyService, Depends(get_host_key_service)]
TlsCertServiceDep = Annotated[TlsCertService, Depends(get_tls_cert_service)]
