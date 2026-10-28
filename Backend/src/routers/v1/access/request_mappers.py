"""Access request response mapping: level progress and decision history."""

from __future__ import annotations

from src.contracts.dto.access.access_request_dto import AccessRequestDTO
from src.contracts.dto.safes.approval_policy_dto import RequestPolicyDTO
from src.contracts.schemas.responses.access.access_request_responses import (
    AccessRequestResponse,
    RequestDecisionResponse,
    RequestLevelResponse,
)
from src.core.enums import RequestStatus
from src.routers.v1.access.briefs import account_brief_response, user_brief_response


def _level_state(dto: AccessRequestDTO, position: int) -> str:
    denied = any(not d.approve and d.level == position for d in dto.decisions)
    if denied:
        return "denied"
    if position < dto.current_level or (
        position == dto.current_level and dto.approved_at is not None
    ):
        return "approved"
    if position == dto.current_level and dto.status == RequestStatus.PENDING:
        return "current"
    return "waiting"


def request_response(dto: AccessRequestDTO) -> AccessRequestResponse:
    policy = RequestPolicyDTO.from_snapshot(dto.policy)
    return AccessRequestResponse(
        id=dto.id,
        account=account_brief_response(dto.account),
        requester=user_brief_response(dto.requester),
        reason=dto.reason,
        ticket_ref=dto.ticket_ref,
        duration_minutes=dto.duration_minutes,
        status=RequestStatus(dto.status),
        decided_by=user_brief_response(dto.decided_by) if dto.decided_by else None,
        decided_at=dto.decided_at,
        decision_note=dto.decision_note,
        expires_at=dto.expires_at,
        created_at=dto.created_at,
        current_level=dto.current_level,
        level_count=len(policy.levels),
        levels=[
            RequestLevelResponse(
                position=lv.position,
                required_approvals=lv.required_approvals,
                approver_type=lv.approver_type,
                approver_key=lv.approver_key,
                approver_name=dto.approver_names.get(lv.approver_key or ""),
                state=_level_state(dto, lv.position),
                approvals=sum(d.approve and d.level == lv.position for d in dto.decisions),
            )
            for lv in policy.levels
        ],
        decisions=[
            RequestDecisionResponse(
                level=d.level,
                approver=user_brief_response(d.approver),
                approve=d.approve,
                note=d.note,
                decided_at=d.decided_at,
            )
            for d in dto.decisions
        ],
        approved_at=dto.approved_at,
        valid_until=dto.expires_at if dto.approved_at else None,
        multi_use=policy.approval_multi_use,
        uses=dto.uses,
    )
