"""Gateway session, command rule and host key service providers.

``build_*`` wire a service from a session for callers without a request (the
gateway, scheduler jobs); the ``get_*`` providers use the same wiring.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.dependencies.audit import build_audit_service
from src.dependencies.database import SQLSessionDep
from src.repositories.inventory.account_repository import AccountRepository
from src.repositories.inventory.target_repository import TargetRepository
from src.repositories.sessions.command_rule_repository import CommandRuleRepository
from src.repositories.sessions.gateway_session_repository import GatewaySessionRepository
from src.services.sessions.command_rule_service import CommandRuleService
from src.services.sessions.host_key_service import HostKeyService
from src.services.sessions.session_service import SessionService


def build_session_service(session: AsyncSession) -> SessionService:
    return SessionService(
        GatewaySessionRepository(session),
        build_audit_service(session),
        Path(get_settings().recording_dir),
    )


def build_command_rule_service(session: AsyncSession) -> CommandRuleService:
    return CommandRuleService(
        CommandRuleRepository(session),
        AccountRepository(session),
        TargetRepository(session),
        build_audit_service(session),
    )


def build_host_key_service(session: AsyncSession) -> HostKeyService:
    return HostKeyService(TargetRepository(session), build_audit_service(session))


async def get_session_service(session: SQLSessionDep) -> SessionService:
    return build_session_service(session)


async def get_command_rule_service(session: SQLSessionDep) -> CommandRuleService:
    return build_command_rule_service(session)


async def get_host_key_service(session: SQLSessionDep) -> HostKeyService:
    return build_host_key_service(session)


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
CommandRuleServiceDep = Annotated[CommandRuleService, Depends(get_command_rule_service)]
HostKeyServiceDep = Annotated[HostKeyService, Depends(get_host_key_service)]
