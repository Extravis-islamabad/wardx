"""Your in-app notifications (no email).

GET  /notifications                  — page through yours (unread_only to filter)
GET  /notifications/unread-count     — how many are unread (the console's bell)
POST /notifications/{id}/read        — mark one read
POST /notifications/read-all         — mark every one read
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from src.contracts.dto.notify.notification_dto import NotificationDTO
from src.contracts.schemas.requests.common import PageParams
from src.contracts.schemas.responses.common import (
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    APIResponse,
    PaginatedAPIResponse,
    ok,
)
from src.contracts.schemas.responses.notify.notification_responses import (
    NotificationResponse,
    UnreadCountResponse,
)
from src.core.permissions import PROFILE_SELF
from src.dependencies.access import NotificationServiceDep
from src.dependencies.auth import ActorDep, require_permission

router = APIRouter(prefix="/notifications", tags=["notifications"])
_GATE = [Depends(require_permission(PROFILE_SELF))]


def _to_response(dto: NotificationDTO) -> NotificationResponse:
    return NotificationResponse(
        id=dto.id,
        kind=dto.kind,
        title=dto.title,
        body=dto.body,
        object_type=dto.object_type,
        object_id=dto.object_id,
        created_at=dto.created_at,
        read_at=dto.read_at,
    )


@router.get(
    "",
    response_model=PaginatedAPIResponse[NotificationResponse],
    dependencies=_GATE,
    summary="Your notifications",
    responses={**UNAUTHORIZED_RESPONSE},
)
async def list_notifications(
    service: NotificationServiceDep,
    actor: ActorDep,
    paging: Annotated[PageParams, Depends()],
    unread_only: bool = False,
) -> PaginatedAPIResponse[NotificationResponse]:
    rows, total = await service.list_mine(
        actor, unread_only=unread_only, page=paging.page, page_size=paging.page_size
    )
    return PaginatedAPIResponse[NotificationResponse](
        data=[_to_response(n) for n in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.get(
    "/unread-count",
    response_model=APIResponse[UnreadCountResponse],
    dependencies=_GATE,
    summary="How many of your notifications are unread",
    responses={**UNAUTHORIZED_RESPONSE},
)
async def unread_count(
    service: NotificationServiceDep, actor: ActorDep
) -> APIResponse[UnreadCountResponse]:
    return ok(UnreadCountResponse(unread=await service.unread_count(actor)))


@router.post(
    "/read-all",
    response_model=APIResponse[UnreadCountResponse],
    dependencies=_GATE,
    summary="Mark all your notifications read",
    responses={**UNAUTHORIZED_RESPONSE},
)
async def read_all(
    service: NotificationServiceDep, actor: ActorDep
) -> APIResponse[UnreadCountResponse]:
    await service.mark_all_read(actor)
    return ok(UnreadCountResponse(unread=0))


@router.post(
    "/{notification_id}/read",
    response_model=APIResponse[None],
    dependencies=_GATE,
    summary="Mark one of your notifications read",
    responses={**UNAUTHORIZED_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def read_one(
    notification_id: uuid.UUID, service: NotificationServiceDep, actor: ActorDep
) -> APIResponse[None]:
    await service.mark_read(actor, notification_id)
    return ok(None)
