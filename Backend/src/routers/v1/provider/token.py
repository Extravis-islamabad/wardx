"""Credential provider token route (docs/phase1/CREDENTIAL_PROVIDER.md §2).

POST /provider/token — client credentials (JSON body or HTTP Basic) for a 5-minute app token

The only public route the provider adds (PUBLIC_ROUTES): it authenticates by client
credentials instead of a codename. Failed attempts are audited and rate-limited per
client_id and per source IP.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from src.contracts.schemas.requests.provider.provider_requests import TokenRequest
from src.contracts.schemas.responses.common import VALIDATION_ERROR_RESPONSE, APIResponse, ok
from src.contracts.schemas.responses.provider.provider_responses import TokenResponse
from src.dependencies.provider import AppAuthServiceDep, provider_source_ip
from src.routers.v1.provider.errors import TOKEN_ERRORS

router = APIRouter(prefix="/provider", tags=["credential provider"])

_basic = HTTPBasic(auto_error=False)


@router.post(
    "/token",
    response_model=APIResponse[TokenResponse],
    summary="Get an application token (client credentials)",
    responses={**TOKEN_ERRORS, **VALIDATION_ERROR_RESPONSE},
)
async def issue_token(
    request: Request,
    response: Response,
    service: AppAuthServiceDep,
    basic: Annotated[HTTPBasicCredentials | None, Depends(_basic)],
    body: TokenRequest | None = None,
) -> APIResponse[TokenResponse]:
    # The JSON body wins when both are sent; HTTP Basic is the alternative.
    client_id = body.client_id if body else basic.username if basic else None
    client_secret = body.client_secret if body else basic.password if basic else None
    token = await service.issue_token(client_id, client_secret, provider_source_ip(request))
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return ok(TokenResponse(access_token=token.access_token, expires_in=token.expires_in))
