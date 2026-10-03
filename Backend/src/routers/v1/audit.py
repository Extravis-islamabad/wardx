from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.contracts.schemas.access import AuditEventOut, ChainVerification, DashboardSummary
from src.contracts.schemas.common import APIResponse, PageParams, PaginatedAPIResponse, ok
from src.dependencies.auth import ActorDep, AuditReader, SessionDep
from src.services import audit_service, dashboard_service

router = APIRouter(tags=["audit"])


@router.get("/audit/events", response_model=PaginatedAPIResponse[AuditEventOut])
async def list_events(
    _: AuditReader,
    session: SessionDep,
    paging: Annotated[PageParams, Depends()],
    action: Annotated[str | None, Query(max_length=80)] = None,
    actor_id: uuid.UUID | None = None,
    object_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
):
    rows, total = await audit_service.list_events(
        session,
        page=paging.page,
        page_size=paging.page_size,
        action=action,
        actor_id=actor_id,
        object_id=object_id,
        since=since,
        until=until,
    )
    return PaginatedAPIResponse[AuditEventOut](
        data=[AuditEventOut.model_validate(e) for e in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.post("/audit/verify", response_model=APIResponse[ChainVerification])
async def verify(_: AuditReader, session: SessionDep):
    result = await audit_service.verify_chain(session)
    return ok(
        ChainVerification(
            ok=result.ok,
            checked=result.checked,
            broken_at_seq=result.broken_at_seq,
            reason=result.reason,
        )
    )


@router.get("/dashboard/summary", response_model=APIResponse[DashboardSummary])
async def summary(actor: ActorDep, session: SessionDep):
    return ok(await dashboard_service.summary(session, actor))
