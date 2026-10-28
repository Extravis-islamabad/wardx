"""Audit service provider.

``build_audit_service`` is the same wiring for callers without a request (the
gateway, scheduler jobs), so every path builds services one way.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.dependencies.database import SQLSessionDep
from src.repositories.audit.audit_event_repository import AuditEventRepository
from src.services.audit.audit_service import AuditService


def build_audit_service(session: AsyncSession) -> AuditService:
    return AuditService(AuditEventRepository(session))


async def get_audit_service(session: SQLSessionDep) -> AuditService:
    return build_audit_service(session)


AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
