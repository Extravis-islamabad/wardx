"""Command rules router — commands the gateway blocks in sessions.

GET    /command-rules             — every rule
POST   /command-rules             — add a rule (one scope: account, target, platform or none)
PATCH  /command-rules/{rule_id}   — change a rule's pattern, description or state
DELETE /command-rules/{rule_id}   — delete a rule
POST   /command-rules/test        — which rule, if any, would block a command
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from src.contracts.dto.sessions.command_rule_dto import CommandRuleDTO
from src.contracts.schemas.requests.sessions.command_rule_requests import (
    CommandRuleCreate,
    CommandRuleUpdate,
    CommandTest,
)
from src.contracts.schemas.responses.common import (
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
    APIResponse,
    ok,
)
from src.contracts.schemas.responses.sessions.command_rule_responses import (
    CommandRuleResponse,
    CommandTestResultResponse,
)
from src.core.permissions import POLICY_MANAGE, POLICY_VIEW
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.sessions import CommandRuleServiceDep

router = APIRouter(prefix="/command-rules", tags=["sessions"])


def _to_response(dto: CommandRuleDTO) -> CommandRuleResponse:
    return CommandRuleResponse(
        id=dto.id,
        pattern=dto.pattern,
        description=dto.description,
        account_id=dto.account_id,
        target_id=dto.target_id,
        platform=dto.platform,
        is_active=dto.is_active,
        created_at=dto.created_at,
    )


@router.get(
    "",
    response_model=APIResponse[list[CommandRuleResponse]],
    dependencies=[Depends(require_permission(POLICY_VIEW))],
    summary="List command rules",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def list_rules(service: CommandRuleServiceDep) -> APIResponse[list[CommandRuleResponse]]:
    return ok([_to_response(r) for r in await service.list()])


@router.post(
    "",
    response_model=APIResponse[CommandRuleResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(POLICY_MANAGE))],
    summary="Create a command rule",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def create_rule(
    request: CommandRuleCreate, service: CommandRuleServiceDep, actor: ActorDep
) -> APIResponse[CommandRuleResponse]:
    return ok(_to_response(await service.create(actor, request.model_dump())))


@router.patch(
    "/{rule_id}",
    response_model=APIResponse[CommandRuleResponse],
    dependencies=[Depends(require_permission(POLICY_MANAGE))],
    summary="Update a command rule",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def update_rule(
    rule_id: uuid.UUID, request: CommandRuleUpdate, service: CommandRuleServiceDep, actor: ActorDep
) -> APIResponse[CommandRuleResponse]:
    changes = request.model_dump(exclude_unset=True)
    return ok(_to_response(await service.update(actor, rule_id, changes)))


@router.delete(
    "/{rule_id}",
    response_model=APIResponse[None],
    dependencies=[Depends(require_permission(POLICY_MANAGE))],
    summary="Delete a command rule",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def delete_rule(
    rule_id: uuid.UUID, service: CommandRuleServiceDep, actor: ActorDep
) -> APIResponse[None]:
    await service.delete(actor, rule_id)
    return ok(None, "Rule deleted")


@router.post(
    "/test",
    response_model=APIResponse[CommandTestResultResponse],
    dependencies=[Depends(require_permission(POLICY_VIEW))],
    summary="Test a command against the rules",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def test_rule(
    request: CommandTest, service: CommandRuleServiceDep
) -> APIResponse[CommandTestResultResponse]:
    result = await service.test_command(request.command, request.account_id)
    return ok(
        CommandTestResultResponse(
            blocked=result.blocked, rule_id=result.rule_id, description=result.description
        )
    )
