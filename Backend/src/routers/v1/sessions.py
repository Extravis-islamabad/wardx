from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from src.contracts.schemas.common import APIResponse, PageParams, PaginatedAPIResponse, ok
from src.contracts.schemas.inventory import TargetOut
from src.contracts.schemas.sessions import (
    CommandRuleCreate,
    CommandRuleOut,
    CommandRuleUpdate,
    CommandTest,
    CommandTestResult,
    GatewayInfo,
    SessionCommandOut,
    SessionOut,
)
from src.core.config import get_settings
from src.dependencies.auth import ActorDep, AdminActor, SessionDep
from src.gateway.naming import SEPARATOR
from src.services import session_service as svc

router = APIRouter(tags=["sessions"])


@router.get("/gateway/info", response_model=APIResponse[GatewayInfo])
async def gateway_info(_: ActorDep):
    s = get_settings()
    return ok(
        GatewayInfo(
            host=s.gateway_public_host,
            port=s.gateway_port,
            login_format=f"<you>{SEPARATOR}<account>{SEPARATOR}<target>",
        )
    )


# ── Sessions ──


@router.get("/sessions", response_model=PaginatedAPIResponse[SessionOut])
async def list_sessions(
    actor: ActorDep,
    session: SessionDep,
    paging: Annotated[PageParams, Depends()],
    status: Annotated[str | None, Query(pattern="^(active|closed|terminated|failed)$")] = None,
    mine: bool = False,
    search: Annotated[str | None, Query(max_length=100)] = None,
):
    rows, total = await svc.list_sessions(
        session,
        actor,
        page=paging.page,
        page_size=paging.page_size,
        status=status,
        mine=mine,
        search=search,
    )
    return PaginatedAPIResponse[SessionOut](
        data=rows, total=total, page=paging.page, page_size=paging.page_size
    )


@router.get("/sessions/{session_id}", response_model=APIResponse[SessionOut])
async def get_session(session_id: uuid.UUID, actor: ActorDep, session: SessionDep):
    return ok(svc.session_out(await svc.get_session_row(session, actor, session_id)))


@router.get("/sessions/{session_id}/commands", response_model=APIResponse[list[SessionCommandOut]])
async def session_commands(session_id: uuid.UUID, actor: ActorDep, session: SessionDep):
    rows = await svc.list_commands(session, actor, session_id)
    return ok([SessionCommandOut.model_validate(r) for r in rows])


@router.get("/sessions/{session_id}/recording")
async def session_recording(session_id: uuid.UUID, actor: ActorDep, session: SessionDep):
    path, verified = await svc.recording(
        session, actor, session_id, Path(get_settings().recording_dir)
    )
    return FileResponse(
        path,
        media_type="application/x-asciicast",
        headers={
            "X-WardX-Recording-Verified": "true" if verified else "false",
            "Cache-Control": "no-store",
        },
    )


@router.post("/sessions/{session_id}/terminate", response_model=APIResponse[SessionOut])
async def terminate_session(session_id: uuid.UUID, actor: AdminActor, session: SessionDep):
    out = await svc.request_terminate(session, actor, session_id)
    return ok(out, "The gateway will disconnect the session within a few seconds")


# ── Command rules ──


@router.get("/command-rules", response_model=APIResponse[list[CommandRuleOut]])
async def list_rules(_: ActorDep, session: SessionDep):
    return ok([CommandRuleOut.model_validate(r) for r in await svc.list_rules(session)])


@router.post("/command-rules", response_model=APIResponse[CommandRuleOut], status_code=201)
async def create_rule(body: CommandRuleCreate, actor: AdminActor, session: SessionDep):
    return ok(CommandRuleOut.model_validate(await svc.create_rule(session, actor, body)))


@router.patch("/command-rules/{rule_id}", response_model=APIResponse[CommandRuleOut])
async def update_rule(
    rule_id: uuid.UUID, body: CommandRuleUpdate, actor: AdminActor, session: SessionDep
):
    return ok(CommandRuleOut.model_validate(await svc.update_rule(session, actor, rule_id, body)))


@router.delete("/command-rules/{rule_id}", response_model=APIResponse[None])
async def delete_rule(rule_id: uuid.UUID, actor: AdminActor, session: SessionDep):
    await svc.delete_rule(session, actor, rule_id)
    return ok(None, "Rule deleted")


@router.post("/command-rules/test", response_model=APIResponse[CommandTestResult])
async def test_rule(body: CommandTest, _: ActorDep, session: SessionDep):
    return ok(await svc.test_command(session, body.command, body.account_id))


# ── Host keys ──


@router.post("/targets/{target_id}/host-key/reset", response_model=APIResponse[TargetOut])
async def reset_host_key(target_id: uuid.UUID, actor: AdminActor, session: SessionDep):
    target = await svc.reset_host_key(session, actor, target_id)
    return ok(TargetOut.model_validate(target), "Host key cleared; the next session pins a new one")
