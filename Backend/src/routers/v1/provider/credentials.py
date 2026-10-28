"""Credential provider fetch routes (docs/phase1/CREDENTIAL_PROVIDER.md §4).

POST /provider/credentials/fetch               — by target (external_ref, address or name) and kind
POST /provider/credentials/{account_id}/fetch  — by account id

Application tokens only (``get_current_app``, codename ``provider.fetch``). POST so
nothing caches or prefetches; every response is ``no-store``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from src.contracts.dto.provider.credential_dto import FetchedCredentialDTO, FetchQueryDTO
from src.contracts.schemas.requests.provider.provider_requests import (
    AccountFetch,
    CredentialFetch,
)
from src.contracts.schemas.responses.common import VALIDATION_ERROR_RESPONSE, APIResponse, ok
from src.contracts.schemas.responses.provider.provider_responses import (
    CredentialResponse,
    CredentialTargetResponse,
)
from src.dependencies.provider import AppPrincipalDep, CredentialServiceDep
from src.routers.v1.provider.errors import FETCH_ERRORS

router = APIRouter(prefix="/provider/credentials", tags=["credential provider"])


def _to_response(dto: FetchedCredentialDTO) -> CredentialResponse:
    c = dto.candidate
    return CredentialResponse(
        account_id=c.account_id,
        target=CredentialTargetResponse(
            id=c.target_id,
            name=c.target_name,
            address=c.target_address,
            external_ref=c.target_external_ref,
        ),
        kind=dto.kind,
        username=c.username,
        secret=dto.secret,
        version_id=dto.version_id,
        max_cache_seconds=dto.max_cache_seconds,
        issued_at=dto.issued_at,
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@router.post(
    "/fetch",
    response_model=APIResponse[CredentialResponse],
    summary="Fetch a credential by target and kind",
    responses={**FETCH_ERRORS, **VALIDATION_ERROR_RESPONSE},
)
async def fetch_credential(
    request: CredentialFetch,
    response: Response,
    app: AppPrincipalDep,
    service: CredentialServiceDep,
) -> APIResponse[CredentialResponse]:
    query = FetchQueryDTO(
        kind=request.kind,
        purpose=request.purpose,
        external_ref=request.target.external_ref,
        address=request.target.address,
        name=request.target.name,
        username=request.username,
    )
    fetched = await service.fetch(app, query)
    _no_store(response)
    return ok(_to_response(fetched))


@router.post(
    "/{account_id}/fetch",
    response_model=APIResponse[CredentialResponse],
    summary="Fetch a credential by account id",
    responses={**FETCH_ERRORS, **VALIDATION_ERROR_RESPONSE},
)
async def fetch_account_credential(
    account_id: uuid.UUID,
    request: AccountFetch,
    response: Response,
    app: AppPrincipalDep,
    service: CredentialServiceDep,
) -> APIResponse[CredentialResponse]:
    fetched = await service.fetch_account(app, account_id, request.purpose)
    _no_store(response)
    return ok(_to_response(fetched))
