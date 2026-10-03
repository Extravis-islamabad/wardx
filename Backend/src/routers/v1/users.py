from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.contracts.schemas.common import APIResponse, PageParams, PaginatedAPIResponse, ok
from src.contracts.schemas.identity import PasswordReset, UserCreate, UserOut, UserUpdate
from src.dependencies.auth import AdminActor, SessionDep
from src.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=PaginatedAPIResponse[UserOut])
async def list_users(
    _: AdminActor,
    session: SessionDep,
    paging: Annotated[PageParams, Depends()],
    search: Annotated[str | None, Query(max_length=100)] = None,
):
    rows, total = await user_service.list_users(
        session, page=paging.page, page_size=paging.page_size, search=search
    )
    return PaginatedAPIResponse[UserOut](
        data=[UserOut.model_validate(u) for u in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.post("", response_model=APIResponse[UserOut], status_code=201)
async def create_user(body: UserCreate, actor: AdminActor, session: SessionDep):
    return ok(UserOut.model_validate(await user_service.create_user(session, actor, body)))


@router.patch("/{user_id}", response_model=APIResponse[UserOut])
async def update_user(user_id: uuid.UUID, body: UserUpdate, actor: AdminActor, session: SessionDep):
    return ok(UserOut.model_validate(await user_service.update_user(session, actor, user_id, body)))


@router.post("/{user_id}/reset-password", response_model=APIResponse[None])
async def reset_password(
    user_id: uuid.UUID, body: PasswordReset, actor: AdminActor, session: SessionDep
):
    await user_service.reset_password(session, actor, user_id, body.new_password)
    return ok(None, "Password reset; the user's sessions were signed out")
