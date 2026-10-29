"""Gateway sessions router.

GET  /sessions                           — page through sessions (yours, or all with
                                           sessions.view_all)
GET  /sessions/{session_id}              — one session
GET  /sessions/{session_id}/commands     — the commands typed, with their verdicts
GET  /sessions/{session_id}/recording    — the asciicast recording (audited, hash-checked)
POST /sessions/{session_id}/terminate    — ask the gateway to disconnect a live session
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from src.contracts.dto.sessions.gateway_session_dto import GatewaySessionDTO, SessionCommandDTO
from src.contracts.schemas.requests.common import PageParams
from src.contracts.schemas.responses.common import (
    CONFLICT_RESPONSE,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    APIResponse,
    PaginatedAPIResponse,
    ok,
)
from src.contracts.schemas.responses.sessions.session_responses import (
    SessionCommandResponse,
    SessionResponse,
)
from src.core.permissions import ACCESS_USE, SESSIONS_TERMINATE
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.sessions import SessionServiceDep

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _to_response(dto: GatewaySessionDTO) -> SessionResponse:
    return SessionResponse(
        id=dto.id,
        user_id=dto.user_id,
        username=dto.username,
        account_id=dto.account_id,
        account_username=dto.account_username,
        target_id=dto.target_id,
        target_name=dto.target_name,
        target_address=dto.target_address,
        protocol=dto.protocol,
        mode=dto.mode,
        exec_command=dto.exec_command,
        client_ip=dto.client_ip,
        gateway_node=dto.gateway_node,
        status=dto.status,
        started_at=dto.started_at,
        ended_at=dto.ended_at,
        close_reason=dto.close_reason,
        terminate_requested_at=dto.terminate_requested_at,
        has_recording=dto.has_recording,
        recording_sha256=dto.recording_sha256,
        recording_bytes=dto.recording_bytes,
        recording_encrypted=dto.recording_encrypted,
        recording_incomplete=dto.recording_incomplete,
        bytes_from_target=dto.bytes_from_target,
        commands_count=dto.commands_count,
        blocked_count=dto.blocked_count,
    )


def _command_response(dto: SessionCommandDTO) -> SessionCommandResponse:
    return SessionCommandResponse(
        id=dto.id,
        occurred_at=dto.occurred_at,
        offset_seconds=dto.offset_seconds,
        command=dto.command,
        verdict=dto.verdict,
        rule_id=dto.rule_id,
    )


@router.get(
    "",
    response_model=PaginatedAPIResponse[SessionResponse],
    dependencies=[Depends(require_permission(ACCESS_USE))],
    summary="List gateway sessions",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def list_sessions(
    service: SessionServiceDep,
    actor: ActorDep,
    paging: Annotated[PageParams, Depends()],
    status: Annotated[str | None, Query(pattern="^(active|closed|terminated|failed)$")] = None,
    mine: bool = False,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> PaginatedAPIResponse[SessionResponse]:
    rows, total = await service.list(
        actor,
        page=paging.page,
        page_size=paging.page_size,
        status=status,
        mine=mine,
        search=search,
    )
    return PaginatedAPIResponse[SessionResponse](
        data=[_to_response(s) for s in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.get(
    "/{session_id}",
    response_model=APIResponse[SessionResponse],
    dependencies=[Depends(require_permission(ACCESS_USE))],
    summary="Get a gateway session",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def get_session(
    session_id: uuid.UUID, service: SessionServiceDep, actor: ActorDep
) -> APIResponse[SessionResponse]:
    return ok(_to_response(await service.get(actor, session_id)))


@router.get(
    "/{session_id}/commands",
    response_model=APIResponse[list[SessionCommandResponse]],
    dependencies=[Depends(require_permission(ACCESS_USE))],
    summary="List the commands typed in a session",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def session_commands(
    session_id: uuid.UUID, service: SessionServiceDep, actor: ActorDep
) -> APIResponse[list[SessionCommandResponse]]:
    rows = await service.commands(actor, session_id)
    return ok([_command_response(r) for r in rows])


@router.get(
    "/{session_id}/recording",
    dependencies=[Depends(require_permission(ACCESS_USE))],
    summary="Download a session recording (asciicast)",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
    },
)
async def session_recording(
    session_id: uuid.UUID, service: SessionServiceDep, actor: ActorDep
) -> Response:
    view = await service.recording(actor, session_id)
    return Response(
        view.data,
        media_type="application/x-asciicast",
        headers={
            "X-WardX-Recording-Verified": "true" if view.verified else "false",
            "X-WardX-Recording-Incomplete": "true" if view.incomplete else "false",
            "X-WardX-Recording-Encrypted": "true" if view.encrypted else "false",
            "Cache-Control": "no-store",
        },
    )


@router.post(
    "/{session_id}/terminate",
    response_model=APIResponse[SessionResponse],
    dependencies=[Depends(require_permission(SESSIONS_TERMINATE))],
    summary="Terminate a live gateway session",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
    },
)
async def terminate_session(
    session_id: uuid.UUID, service: SessionServiceDep, actor: ActorDep
) -> APIResponse[SessionResponse]:
    out = await service.request_terminate(actor, session_id)
    return ok(_to_response(out), "The gateway will disconnect the session within a few seconds")
