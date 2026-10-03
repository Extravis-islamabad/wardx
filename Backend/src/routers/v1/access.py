from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from src.contracts.schemas.access import (
    CheckoutCreate,
    CheckoutOut,
    RequestCreate,
    RequestDecision,
    RequestOut,
    RevealedSecret,
)
from src.contracts.schemas.common import APIResponse, PageParams, PaginatedAPIResponse, ok
from src.core.config import get_settings
from src.core.enums import CheckoutStatus, RequestStatus
from src.dependencies.auth import ActorDep, ApproverActor, SessionDep
from src.services import access_service as svc

router = APIRouter(tags=["access"])


# ── Requests ──


@router.get("/requests", response_model=PaginatedAPIResponse[RequestOut])
async def list_requests(
    actor: ActorDep,
    session: SessionDep,
    paging: Annotated[PageParams, Depends()],
    status: RequestStatus | None = None,
    mine: bool = False,
):
    rows, total = await svc.list_requests(
        session, actor, page=paging.page, page_size=paging.page_size, status=status, mine=mine
    )
    return PaginatedAPIResponse[RequestOut](
        data=rows, total=total, page=paging.page, page_size=paging.page_size
    )


@router.post("/requests", response_model=APIResponse[RequestOut], status_code=201)
async def create_request(body: RequestCreate, actor: ActorDep, session: SessionDep):
    return ok(await svc.create_request(session, get_settings(), actor, body))


@router.post("/requests/{request_id}/decision", response_model=APIResponse[RequestOut])
async def decide_request(
    request_id: uuid.UUID, body: RequestDecision, actor: ApproverActor, session: SessionDep
):
    return ok(
        await svc.decide_request(
            session, get_settings(), actor, request_id, approve=body.approve, note=body.note
        )
    )


@router.post("/requests/{request_id}/cancel", response_model=APIResponse[RequestOut])
async def cancel_request(request_id: uuid.UUID, actor: ActorDep, session: SessionDep):
    return ok(await svc.cancel_request(session, actor, request_id))


# ── Check-outs ──


@router.get("/checkouts", response_model=PaginatedAPIResponse[CheckoutOut])
async def list_checkouts(
    actor: ActorDep,
    session: SessionDep,
    paging: Annotated[PageParams, Depends()],
    status: CheckoutStatus | None = None,
    mine: bool = False,
):
    rows, total = await svc.list_checkouts(
        session, actor, page=paging.page, page_size=paging.page_size, status=status, mine=mine
    )
    return PaginatedAPIResponse[CheckoutOut](
        data=rows, total=total, page=paging.page, page_size=paging.page_size
    )


@router.post("/checkouts", response_model=APIResponse[CheckoutOut], status_code=201)
async def create_checkout(body: CheckoutCreate, actor: ActorDep, session: SessionDep):
    return ok(await svc.checkout(session, actor, body))


@router.post("/checkouts/{checkout_id}/reveal", response_model=APIResponse[RevealedSecret])
async def reveal(checkout_id: uuid.UUID, actor: ActorDep, session: SessionDep, response: Response):
    # POST, not GET: a reveal is an audited action, and must never be cached or prefetched.
    response.headers["Cache-Control"] = "no-store"
    return ok(await svc.reveal(session, actor, checkout_id))


@router.post("/checkouts/{checkout_id}/checkin", response_model=APIResponse[CheckoutOut])
async def checkin(checkout_id: uuid.UUID, actor: ActorDep, session: SessionDep):
    return ok(await svc.checkin(session, actor, checkout_id))
