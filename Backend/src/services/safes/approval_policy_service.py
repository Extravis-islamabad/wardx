"""Safe approval policies: read and replace, with validation.

Rules:
- Reading needs safes.manage or 'list' on the safe; saving needs safes.manage (route).
- approval_required needs at least one level; at most ``MAX_LEVELS`` levels, ordered as
  given. Each needs at least one approval.
- A named user approver must exist, be active and hold 'approve' on the safe; a named
  group approver must be a group member of the safe holding 'approve'.
- The ticket pattern must be a safe regex (see ticket_validator.check_pattern).
- Every save is audited with before and after.
"""

from __future__ import annotations

import uuid

from src.contracts.dto.safes.approval_policy_dto import ApprovalLevelDTO, ApprovalPolicyDTO
from src.core.context import Actor
from src.core.enums import ApproverType, PrincipalType, SafePermission, TicketMode
from src.core.permissions import SAFES_MANAGE
from src.directory.ldap_client import normalise_dn
from src.errors.exceptions import AppError, NotFoundError
from src.repositories.safes.approval_policy_repository import ApprovalPolicyRepository
from src.repositories.safes.safe_member_repository import SafeMemberRepository
from src.services.access.ticket_validator import check_pattern
from src.services.audit.audit_service import AuditService
from src.services.safes.safe_access_service import SafeAccessService

MAX_LEVELS = 5


class InvalidPolicy(AppError):
    status_code = 422
    code = "invalid_policy"


class ApprovalPolicyService:
    def __init__(
        self,
        policies: ApprovalPolicyRepository,
        members: SafeMemberRepository,
        access: SafeAccessService,
        audit: AuditService,
    ) -> None:
        self._policies = policies
        self._members = members
        self._access = access
        self._audit = audit

    async def policy(self, safe_id: uuid.UUID) -> ApprovalPolicyDTO:
        found = await self._policies.get(safe_id)
        if found is None:
            raise NotFoundError("Safe not found")
        return found

    async def get(self, actor: Actor, safe_id: uuid.UUID) -> ApprovalPolicyDTO:
        if not actor.can(SAFES_MANAGE):
            await self._access.require(actor, safe_id, what="Safe")
        return await self.policy(safe_id)

    async def _check_level(
        self, safe_id: uuid.UUID, position: int, level: dict, holders: set[uuid.UUID]
    ) -> ApprovalLevelDTO:
        kind = ApproverType(level["approver_type"])
        key = (level.get("approver_key") or "").strip() or None
        if kind == ApproverType.SAFE_APPROVERS:
            key = None
        elif key is None:
            raise InvalidPolicy(f"Level {position}: name the {kind.value} approver")
        elif kind == ApproverType.USER:
            try:
                user_id = uuid.UUID(key)
            except ValueError as exc:
                raise InvalidPolicy(f"Level {position}: a user is named by their id") from exc
            if user_id not in holders:
                raise InvalidPolicy(
                    f"Level {position}: that user must be active and hold 'approve' on the safe"
                )
            key = str(user_id)
        else:
            key = normalise_dn(key)
            members = await self._members.list_for_safe(safe_id)
            if not any(
                m.principal_type == PrincipalType.GROUP
                and m.principal_key == key
                and SafePermission.APPROVE in m.permissions
                for m in members
            ):
                raise InvalidPolicy(
                    f"Level {position}: that group must be a member of the safe with 'approve'"
                )
        return ApprovalLevelDTO(
            position=position,
            required_approvals=int(level["required_approvals"]),
            approver_type=kind.value,
            approver_key=key,
        )

    async def save(
        self, actor: Actor, safe_id: uuid.UUID, values: dict, levels: list[dict]
    ) -> ApprovalPolicyDTO:
        before = await self.policy(safe_id)
        if values["approval_required"] and not levels:
            raise InvalidPolicy("A safe that requires approval needs at least one level")
        if len(levels) > MAX_LEVELS:
            raise InvalidPolicy(f"At most {MAX_LEVELS} approval levels")
        pattern = (values.get("ticket_pattern") or "").strip() or None
        if pattern:
            check_pattern(pattern)
        holders = await self._policies.approve_holders(safe_id)
        checked = [
            await self._check_level(safe_id, i, lv, holders) for i, lv in enumerate(levels, 1)
        ]
        stored = {
            **values,
            "ticket_mode": TicketMode(values["ticket_mode"]).value,
            "ticket_pattern": pattern,
        }
        await self._policies.save(safe_id, stored, checked)
        after = await self.policy(safe_id)
        await self._audit.record(
            actor,
            "safe.policy_update",
            object_type="safe",
            object_id=safe_id,
            details={"before": before.audit_view(), "after": after.audit_view()},
        )
        await self._policies.commit()
        return after
