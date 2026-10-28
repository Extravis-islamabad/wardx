"""Privileged accounts router.

GET    /accounts                     — page through accounts (target, safe, search)
GET    /accounts/{account_id}        — one account
POST   /accounts                     — add an account, optionally with its secret
PATCH  /accounts/{account_id}        — change check-out policy
PUT    /accounts/{account_id}/secret — store a new secret version
DELETE /accounts/{account_id}        — delete an account and every secret version
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from src.contracts.dto.inventory.account_dto import AccountDTO, AccountFilterDTO
from src.contracts.schemas.requests.common import PageParams
from src.contracts.schemas.requests.inventory.account_requests import (
    AccountCreate,
    AccountUpdate,
    SecretSet,
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
from src.contracts.schemas.responses.inventory.account_responses import (
    AccountResponse,
    SafeBriefResponse,
    TargetBriefResponse,
)
from src.core.permissions import INVENTORY_MANAGE, INVENTORY_VIEW
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.inventory import AccountServiceDep

router = APIRouter(prefix="/accounts", tags=["inventory"])


def account_response(dto: AccountDTO) -> AccountResponse:
    """Shared with the break-glass router."""
    return AccountResponse(
        id=dto.id,
        target=TargetBriefResponse(
            id=dto.target.id,
            name=dto.target.name,
            address=dto.target.address,
            platform=dto.target.platform,
            protocol=dto.target.protocol,
        ),
        safe=SafeBriefResponse(id=dto.safe.id, name=dto.safe.name),
        username=dto.username,
        secret_type=dto.secret_type,
        description=dto.description,
        has_secret=dto.has_secret,
        secret_version=dto.secret_version,
        secret_updated_at=dto.secret_updated_at,
        requires_approval=dto.requires_approval,
        exclusive_checkout=dto.exclusive_checkout,
        max_checkout_minutes=dto.max_checkout_minutes,
        active_checkouts=dto.active_checkouts,
        created_at=dto.created_at,
        rotation_interval_days=dto.rotation_interval_days,
        rotate_after_use=dto.rotate_after_use,
        password_length=dto.password_length,
        reconcile_account_id=dto.reconcile_account_id,
        sync_status=dto.sync_status,
        last_verified_at=dto.last_verified_at,
        last_verify_method=dto.last_verify_method,
        last_rotated_at=dto.last_rotated_at,
        last_rotation_status=dto.last_rotation_status,
        rotation_status=dto.rotation_status,
        risk_flags=list(dto.risk_flags),
    )


@router.get(
    "",
    response_model=PaginatedAPIResponse[AccountResponse],
    dependencies=[Depends(require_permission(INVENTORY_VIEW))],
    summary="List privileged accounts",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def list_accounts(
    service: AccountServiceDep,
    actor: ActorDep,
    paging: Annotated[PageParams, Depends()],
    target_id: uuid.UUID | None = None,
    safe_id: uuid.UUID | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> PaginatedAPIResponse[AccountResponse]:
    rows, total = await service.list(
        actor,
        AccountFilterDTO(target_id=target_id, safe_id=safe_id, search=search),
        page=paging.page,
        page_size=paging.page_size,
    )
    return PaginatedAPIResponse[AccountResponse](
        data=[account_response(a) for a in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.get(
    "/{account_id}",
    response_model=APIResponse[AccountResponse],
    dependencies=[Depends(require_permission(INVENTORY_VIEW))],
    summary="Get a privileged account",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def get_account(
    account_id: uuid.UUID, service: AccountServiceDep, actor: ActorDep
) -> APIResponse[AccountResponse]:
    return ok(account_response(await service.get_visible(actor, account_id)))


@router.post(
    "",
    response_model=APIResponse[AccountResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(INVENTORY_MANAGE))],
    summary="Create a privileged account",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def create_account(
    request: AccountCreate, service: AccountServiceDep, actor: ActorDep
) -> APIResponse[AccountResponse]:
    account = await service.create(actor, request.model_dump(exclude={"secret"}), request.secret)
    return ok(account_response(account))


@router.patch(
    "/{account_id}",
    response_model=APIResponse[AccountResponse],
    dependencies=[Depends(require_permission(INVENTORY_MANAGE))],
    summary="Update an account's check-out policy",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def update_account(
    account_id: uuid.UUID, request: AccountUpdate, service: AccountServiceDep, actor: ActorDep
) -> APIResponse[AccountResponse]:
    changes = request.model_dump(exclude_unset=True)
    return ok(account_response(await service.update(actor, account_id, changes)))


@router.put(
    "/{account_id}/secret",
    response_model=APIResponse[AccountResponse],
    dependencies=[Depends(require_permission(INVENTORY_MANAGE))],
    summary="Store a new secret version for an account",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def set_secret(
    account_id: uuid.UUID, request: SecretSet, service: AccountServiceDep, actor: ActorDep
) -> APIResponse[AccountResponse]:
    account = await service.set_secret(actor, account_id, request.value)
    return ok(account_response(account), "Secret stored")


@router.delete(
    "/{account_id}",
    response_model=APIResponse[None],
    dependencies=[Depends(require_permission(INVENTORY_MANAGE))],
    summary="Delete an account and every version of its secret",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
    },
)
async def delete_account(
    account_id: uuid.UUID, service: AccountServiceDep, actor: ActorDep
) -> APIResponse[None]:
    await service.delete(actor, account_id)
    return ok(None, "Account and its secrets deleted")
