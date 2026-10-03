from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.contracts.schemas.common import APIResponse, PageParams, PaginatedAPIResponse, ok
from src.contracts.schemas.inventory import (
    AccountCreate,
    AccountOut,
    AccountUpdate,
    SecretSet,
    TargetCreate,
    TargetOut,
    TargetUpdate,
)
from src.core.enums import Platform
from src.dependencies.auth import ActorDep, AdminActor, SessionDep
from src.services import inventory_service as svc

router = APIRouter(tags=["inventory"])


# ── Targets ──


@router.get("/targets", response_model=PaginatedAPIResponse[TargetOut])
async def list_targets(
    _: ActorDep,
    session: SessionDep,
    paging: Annotated[PageParams, Depends()],
    search: Annotated[str | None, Query(max_length=100)] = None,
    platform: Platform | None = None,
):
    rows, total = await svc.list_targets(
        session, page=paging.page, page_size=paging.page_size, search=search, platform=platform
    )
    return PaginatedAPIResponse[TargetOut](
        data=[TargetOut.model_validate(t) for t in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.get("/targets/{target_id}", response_model=APIResponse[TargetOut])
async def get_target(target_id: uuid.UUID, _: ActorDep, session: SessionDep):
    return ok(TargetOut.model_validate(await svc.get_target(session, target_id)))


@router.post("/targets", response_model=APIResponse[TargetOut], status_code=201)
async def create_target(body: TargetCreate, actor: AdminActor, session: SessionDep):
    return ok(TargetOut.model_validate(await svc.create_target(session, actor, body)))


@router.patch("/targets/{target_id}", response_model=APIResponse[TargetOut])
async def update_target(
    target_id: uuid.UUID, body: TargetUpdate, actor: AdminActor, session: SessionDep
):
    return ok(TargetOut.model_validate(await svc.update_target(session, actor, target_id, body)))


@router.delete("/targets/{target_id}", response_model=APIResponse[None])
async def delete_target(target_id: uuid.UUID, actor: AdminActor, session: SessionDep):
    await svc.delete_target(session, actor, target_id)
    return ok(None, "Target and its accounts deleted")


# ── Accounts ──


@router.get("/accounts", response_model=PaginatedAPIResponse[AccountOut])
async def list_accounts(
    _: ActorDep,
    session: SessionDep,
    paging: Annotated[PageParams, Depends()],
    target_id: uuid.UUID | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
):
    rows, total = await svc.list_accounts(
        session, page=paging.page, page_size=paging.page_size, target_id=target_id, search=search
    )
    return PaginatedAPIResponse[AccountOut](
        data=rows, total=total, page=paging.page, page_size=paging.page_size
    )


@router.get("/accounts/{account_id}", response_model=APIResponse[AccountOut])
async def get_account(account_id: uuid.UUID, _: ActorDep, session: SessionDep):
    account = await svc.get_account(session, account_id)
    counts = await svc.active_checkout_counts(session, [account.id])
    return ok(svc.account_out(account, counts.get(account.id, 0)))


@router.post("/accounts", response_model=APIResponse[AccountOut], status_code=201)
async def create_account(body: AccountCreate, actor: AdminActor, session: SessionDep):
    return ok(await svc.create_account(session, actor, body))


@router.patch("/accounts/{account_id}", response_model=APIResponse[AccountOut])
async def update_account(
    account_id: uuid.UUID, body: AccountUpdate, actor: AdminActor, session: SessionDep
):
    return ok(await svc.update_account(session, actor, account_id, body))


@router.put("/accounts/{account_id}/secret", response_model=APIResponse[AccountOut])
async def set_secret(
    account_id: uuid.UUID, body: SecretSet, actor: AdminActor, session: SessionDep
):
    return ok(await svc.set_secret(session, actor, account_id, body.value), "Secret stored")


@router.delete("/accounts/{account_id}", response_model=APIResponse[None])
async def delete_account(account_id: uuid.UUID, actor: AdminActor, session: SessionDep):
    await svc.delete_account(session, actor, account_id)
    return ok(None, "Account and its secrets deleted")
