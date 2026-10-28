"""Application identities router (apps.manage).

GET    /apps                              — page through application identities
GET    /apps/{app_id}                     — one app with its secrets (prefixes only)
POST   /apps                              — create an app; its first client secret is shown once
PATCH  /apps/{app_id}                     — change name, allowlist, rate limit, enable or disable
POST   /apps/{app_id}/secrets             — add a client secret (at most two active), shown once
POST   /apps/{app_id}/secrets/{secret_id}/revoke — revoke a secret at once
GET    /apps/{app_id}/fetches             — the app's recent fetches, from the audit trail
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from src.contracts.dto.audit.audit_event_dto import AuditEventDTO
from src.contracts.dto.provider.app_dto import AppDTO, NewAppSecretDTO
from src.contracts.schemas.requests.common import PageParams
from src.contracts.schemas.requests.provider.app_requests import (
    AppCreate,
    AppSecretCreate,
    AppUpdate,
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
from src.contracts.schemas.responses.provider.provider_responses import (
    AppFetchEventResponse,
    AppResponse,
    AppSecretResponse,
    NewAppSecretResponse,
)
from src.core.permissions import APPS_MANAGE
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.provider import AppServiceDep
from src.models import utcnow

router = APIRouter(
    prefix="/apps",
    tags=["credential provider"],
    dependencies=[Depends(require_permission(APPS_MANAGE))],
)

_WRITE_ERRORS = {
    **UNAUTHORIZED_RESPONSE,
    **FORBIDDEN_RESPONSE,
    **NOT_FOUND_RESPONSE,
    **CONFLICT_RESPONSE,
    **VALIDATION_ERROR_RESPONSE,
}


def _to_response(dto: AppDTO) -> AppResponse:
    now = utcnow()
    secrets = [
        AppSecretResponse(
            id=s.id,
            slot=s.slot,
            prefix=s.prefix,
            status="revoked" if s.revoked_at else "active" if s.is_active(now) else "expired",
            expires_at=s.expires_at,
            revoked_at=s.revoked_at,
            last_used_at=s.last_used_at,
            created_at=s.created_at,
        )
        for s in dto.secrets
    ]
    return AppResponse(
        id=dto.id,
        name=dto.name,
        description=dto.description,
        client_id=dto.client_id,
        enabled=dto.enabled,
        ip_allowlist=list(dto.ip_allowlist),
        rate_limit_per_minute=dto.rate_limit_per_minute,
        usable=dto.enabled
        and bool(dto.ip_allowlist)
        and any(s.status == "active" for s in secrets),
        secrets=secrets,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def _new_secret(dto: NewAppSecretDTO) -> NewAppSecretResponse:
    return NewAppSecretResponse(
        app=_to_response(dto.app),
        secret_id=dto.secret.id,
        client_id=dto.app.client_id,
        client_secret=dto.client_secret,
    )


def _fetch_event(e: AuditEventDTO) -> AppFetchEventResponse:
    d = e.details or {}
    return AppFetchEventResponse(
        occurred_at=e.occurred_at,
        outcome=e.outcome,
        source_ip=e.source_ip,
        kind=d.get("kind"),
        purpose=d.get("purpose"),
        account_id=d.get("account_id"),
        target_id=d.get("target_id"),
        username=d.get("username"),
        version_id=d.get("version_id"),
        error_code=d.get("error_code"),
    )


@router.get(
    "",
    response_model=PaginatedAPIResponse[AppResponse],
    summary="List application identities",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def list_apps(
    service: AppServiceDep,
    paging: Annotated[PageParams, Depends()],
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> PaginatedAPIResponse[AppResponse]:
    rows, total = await service.list(search=search, page=paging.page, page_size=paging.page_size)
    return PaginatedAPIResponse[AppResponse](
        data=[_to_response(a) for a in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.get(
    "/{app_id}",
    response_model=APIResponse[AppResponse],
    summary="Get an application identity",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def get_app(app_id: uuid.UUID, service: AppServiceDep) -> APIResponse[AppResponse]:
    return ok(_to_response(await service.get(app_id)))


@router.post(
    "",
    response_model=APIResponse[NewAppSecretResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create an application identity (its client secret is shown once)",
    responses=_WRITE_ERRORS,
)
async def create_app(
    request: AppCreate, service: AppServiceDep, actor: ActorDep
) -> APIResponse[NewAppSecretResponse]:
    values = request.model_dump(exclude={"secret_expires_at"})
    created = await service.create(actor, values, request.secret_expires_at)
    return ok(_new_secret(created), "Copy the client secret now: it is not shown again")


@router.patch(
    "/{app_id}",
    response_model=APIResponse[AppResponse],
    summary="Change an application identity",
    responses=_WRITE_ERRORS,
)
async def update_app(
    app_id: uuid.UUID, request: AppUpdate, service: AppServiceDep, actor: ActorDep
) -> APIResponse[AppResponse]:
    changes = {k: v for k, v in request.model_dump(exclude_unset=True).items() if v is not None}
    if "description" in request.model_fields_set:
        changes["description"] = request.description
    return ok(_to_response(await service.update(actor, app_id, changes)))


@router.post(
    "/{app_id}/secrets",
    response_model=APIResponse[NewAppSecretResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Add a client secret (at most two active; shown once)",
    responses=_WRITE_ERRORS,
)
async def add_secret(
    app_id: uuid.UUID, request: AppSecretCreate, service: AppServiceDep, actor: ActorDep
) -> APIResponse[NewAppSecretResponse]:
    created = await service.add_secret(actor, app_id, request.expires_at)
    return ok(_new_secret(created), "Copy the client secret now: it is not shown again")


@router.post(
    "/{app_id}/secrets/{secret_id}/revoke",
    response_model=APIResponse[AppResponse],
    summary="Revoke a client secret",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
    },
)
async def revoke_secret(
    app_id: uuid.UUID, secret_id: uuid.UUID, service: AppServiceDep, actor: ActorDep
) -> APIResponse[AppResponse]:
    return ok(_to_response(await service.revoke_secret(actor, app_id, secret_id)), "Revoked")


@router.get(
    "/{app_id}/fetches",
    response_model=PaginatedAPIResponse[AppFetchEventResponse],
    summary="An application identity's recent fetches",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def recent_fetches(
    app_id: uuid.UUID, service: AppServiceDep, paging: Annotated[PageParams, Depends()]
) -> PaginatedAPIResponse[AppFetchEventResponse]:
    rows, total = await service.recent_fetches(app_id, page=paging.page, page_size=paging.page_size)
    return PaginatedAPIResponse[AppFetchEventResponse](
        data=[_fetch_event(e) for e in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )
