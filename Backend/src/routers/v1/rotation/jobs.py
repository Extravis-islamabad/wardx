"""Rotation jobs router.

GET  /rotation/jobs                  — jobs of accounts in safes you can list (filters)
GET  /rotation/jobs/{job_id}         — one job with its step timeline (redacted transcripts)
POST /rotation/jobs/{job_id}/resolve — resolve a job that needs attention (manage_accounts)
GET  /rotation/attention             — needs attention, out of sync, untrustworthy, empty
                                       passwords and overdue waits, in your safes
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.contracts.dto.rotation.rotation_dto import RotationFilterDTO
from src.contracts.schemas.requests.common import PageParams
from src.contracts.schemas.requests.rotation.rotation_requests import ResolveIn
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
from src.contracts.schemas.responses.rotation.rotation_responses import (
    RotationAttentionResponse,
    RotationJobResponse,
)
from src.core.permissions import INVENTORY_MANAGE, INVENTORY_VIEW
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.rotation import RotationReviewServiceDep, RotationServiceDep
from src.routers.v1.rotation.mappers import account_brief, job_response

router = APIRouter(prefix="/rotation", tags=["rotation"])


@router.get(
    "/jobs",
    response_model=PaginatedAPIResponse[RotationJobResponse],
    dependencies=[Depends(require_permission(INVENTORY_VIEW))],
    summary="List rotation jobs",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def list_jobs(
    service: RotationServiceDep,
    actor: ActorDep,
    paging: Annotated[PageParams, Depends()],
    status: Annotated[str | None, Query(max_length=24)] = None,
    reason: Annotated[str | None, Query(max_length=20)] = None,
    account_id: uuid.UUID | None = None,
) -> PaginatedAPIResponse[RotationJobResponse]:
    rows, total = await service.list_jobs(
        actor,
        RotationFilterDTO(status=status, reason=reason, account_id=account_id),
        page=paging.page,
        page_size=paging.page_size,
    )
    return PaginatedAPIResponse[RotationJobResponse](
        data=[job_response(j) for j in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=APIResponse[RotationJobResponse],
    dependencies=[Depends(require_permission(INVENTORY_VIEW))],
    summary="A rotation job with its steps",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def get_job(
    job_id: uuid.UUID, service: RotationServiceDep, actor: ActorDep
) -> APIResponse[RotationJobResponse]:
    return ok(job_response(await service.get_job(actor, job_id)))


@router.post(
    "/jobs/{job_id}/resolve",
    response_model=APIResponse[RotationJobResponse],
    dependencies=[Depends(require_permission(INVENTORY_MANAGE))],
    summary="Resolve a rotation job that needs attention",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def resolve(
    job_id: uuid.UUID, request: ResolveIn, service: RotationReviewServiceDep, actor: ActorDep
) -> APIResponse[RotationJobResponse]:
    job = await service.resolve(actor, job_id, request.action, request.note, request.secret)
    return ok(job_response(job), "Resolved")


@router.get(
    "/attention",
    response_model=APIResponse[RotationAttentionResponse],
    dependencies=[Depends(require_permission(INVENTORY_VIEW))],
    summary="Rotation problems in the safes you can list",
    responses={**UNAUTHORIZED_RESPONSE},
)
async def attention(
    service: RotationServiceDep, actor: ActorDep
) -> APIResponse[RotationAttentionResponse]:
    a = await service.attention(actor)
    return ok(
        RotationAttentionResponse(
            needs_attention=[job_response(j) for j in a.needs_attention],
            out_of_sync=[account_brief(x) for x in a.out_of_sync],
            verify_untrustworthy=[account_brief(x) for x in a.untrustworthy],
            confirmed_untrustworthy=[account_brief(x) for x in a.confirmed_untrustworthy],
            empty_password=[account_brief(x) for x in a.empty_password],
            release_overdue=[job_response(j) for j in a.release_overdue],
        )
    )
