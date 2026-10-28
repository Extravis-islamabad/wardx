"""User administration router.

GET   /users                            — page through users (search)
POST  /users                            — create a local user
PATCH /users/{user_id}                  — change profile, role or active state
POST  /users/{user_id}/reset-password   — set a new password (signs the user out)
POST  /users/{user_id}/mfa/reset        — remove a user's MFA so they re-enrol
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from src.contracts.dto.identity.user_dto import UserFilterDTO
from src.contracts.schemas.requests.common import PageParams
from src.contracts.schemas.requests.identity.user_requests import (
    PasswordReset,
    UserCreate,
    UserUpdate,
)
from src.contracts.schemas.responses.common import (
    CONFLICT_RESPONSE,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
    APIResponse,
    PaginatedAPIResponse,
    ok,
)
from src.contracts.schemas.responses.identity.user_responses import UserResponse
from src.core.permissions import USERS_MANAGE
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.identity import MfaServiceDep, UserServiceDep
from src.routers.v1.identity.mappers import user_response

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "",
    response_model=PaginatedAPIResponse[UserResponse],
    dependencies=[Depends(require_permission(USERS_MANAGE))],
    summary="List users",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def list_users(
    service: UserServiceDep,
    paging: Annotated[PageParams, Depends()],
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> PaginatedAPIResponse[UserResponse]:
    rows, total = await service.list(
        UserFilterDTO(search=search), page=paging.page, page_size=paging.page_size
    )
    return PaginatedAPIResponse[UserResponse](
        data=[user_response(u) for u in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.post(
    "",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(USERS_MANAGE))],
    summary="Create a local user",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def create_user(
    request: UserCreate, service: UserServiceDep, actor: ActorDep
) -> APIResponse[UserResponse]:
    user = await service.create(
        actor,
        username=request.username,
        password=request.password,
        email=request.email,
        full_name=request.full_name,
        role=request.role,
    )
    return ok(user_response(user))


@router.patch(
    "/{user_id}",
    response_model=APIResponse[UserResponse],
    dependencies=[Depends(require_permission(USERS_MANAGE))],
    summary="Update a user",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def update_user(
    user_id: uuid.UUID, request: UserUpdate, service: UserServiceDep, actor: ActorDep
) -> APIResponse[UserResponse]:
    changes = request.model_dump(exclude_unset=True)
    return ok(user_response(await service.update(actor, user_id, changes)))


@router.post(
    "/{user_id}/reset-password",
    response_model=APIResponse[None],
    dependencies=[Depends(require_permission(USERS_MANAGE))],
    summary="Reset a user's password",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def reset_password(
    user_id: uuid.UUID, request: PasswordReset, service: UserServiceDep, actor: ActorDep
) -> APIResponse[None]:
    await service.reset_password(actor, user_id, request.new_password)
    return ok(None, "Password reset; the user's sessions were signed out")


@router.post(
    "/{user_id}/mfa/reset",
    response_model=APIResponse[None],
    dependencies=[Depends(require_permission(USERS_MANAGE))],
    summary="Remove a user's MFA",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def reset_mfa(
    user_id: uuid.UUID, service: MfaServiceDep, actor: ActorDep
) -> APIResponse[None]:
    await service.admin_reset(actor, user_id)
    return ok(None, "MFA removed; the user sets it up again at next sign-in")
