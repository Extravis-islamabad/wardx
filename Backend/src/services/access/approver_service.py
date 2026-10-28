"""Who may decide a request at its current level, and who to notify.

Eligible at a level: holds 'approve' on the account's safe (any membership: user, role
or directory group), is not the requester, has not decided this request before (one
decision per person, so nobody approves at two levels), and matches the level:
- ``safe_approvers``: any such holder;
- ``user``: that user;
- ``group``: a member of that directory group (group cache; unverifiable groups count
  as none, so a group level fails closed while the directory is down).
"""

from __future__ import annotations

import uuid

from src.contracts.dto.access.access_request_dto import AccessRequestDTO
from src.contracts.dto.safes.approval_policy_dto import ApprovalLevelDTO, RequestPolicyDTO
from src.core.context import Actor
from src.core.enums import ApproverType, SafePermission
from src.repositories.safes.approval_policy_repository import ApprovalPolicyRepository
from src.services.safes.safe_access_service import SafeAccessService


def current_level(request: AccessRequestDTO) -> ApprovalLevelDTO | None:
    return RequestPolicyDTO.from_snapshot(request.policy).level(request.current_level)


class ApproverService:
    def __init__(self, access: SafeAccessService, policies: ApprovalPolicyRepository) -> None:
        self._access = access
        self._policies = policies

    async def why_not(self, actor: Actor, request: AccessRequestDTO) -> str | None:
        """None when the actor may decide the request now; otherwise the reason."""
        if request.requester_id == actor.id:
            return "You cannot decide your own request"
        if any(d.approver.id == actor.id for d in request.decisions):
            return "You have already decided this request; one decision per person"
        level = current_level(request)
        if level is None:
            return "This request has no approval level to decide"
        safe_id = request.account.safe_id
        if SafePermission.APPROVE not in await self._access.permissions(actor, safe_id):
            return "You need 'approve' on this account's safe"
        kind = ApproverType(level.approver_type)
        if kind == ApproverType.USER and level.approver_key != str(actor.id):
            return f"Level {level.position} is decided by a named user"
        if kind == ApproverType.GROUP:
            principals = await self._access.principals(actor)
            if level.approver_key not in principals.groups:
                return f"Level {level.position} is decided by members of a directory group"
        return None

    async def recipients(self, request: AccessRequestDTO) -> set[uuid.UUID]:
        """Everyone who can decide the request's current level (from the group cache)."""
        level = current_level(request)
        if level is None or request.account.safe_id is None:
            return set()
        holders = await self._policies.approve_holders(request.account.safe_id)
        kind = ApproverType(level.approver_type)
        if kind == ApproverType.USER:
            holders &= {uuid.UUID(level.approver_key)}
        elif kind == ApproverType.GROUP:
            holders &= await self._policies.group_user_ids([level.approver_key])
        decided = {d.approver.id for d in request.decisions}
        return holders - decided - {request.requester_id}
