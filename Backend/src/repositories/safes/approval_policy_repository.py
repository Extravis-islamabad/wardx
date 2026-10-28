"""Safe approval policies (inventory.safes policy columns + safe_approval_levels), and who
holds 'approve' on a safe (for notifying approvers)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import String, cast, delete, select

from src.contracts.dto.safes.approval_policy_dto import ApprovalLevelDTO, ApprovalPolicyDTO
from src.core.enums import PrincipalType, SafePermission
from src.models import Safe, SafeApprovalLevel, SafeMember, User, UserGroupCache
from src.repositories.base import BaseRepository
from src.repositories.identity.user_names import display_names

POLICY_FIELDS = (
    "approval_required",
    "ticket_mode",
    "ticket_pattern",
    "approval_window_minutes",
    "approval_multi_use",
    "level_timeout_hours",
)


class ApprovalPolicyRepository(BaseRepository):
    async def get(self, safe_id: uuid.UUID) -> ApprovalPolicyDTO | None:
        safe = await self._session.get(Safe, safe_id, populate_existing=True)
        if safe is None:
            return None
        levels = list(
            await self._session.scalars(
                select(SafeApprovalLevel)
                .where(SafeApprovalLevel.safe_id == safe_id)
                .order_by(SafeApprovalLevel.position)
            )
        )
        names = await display_names(
            self._session, (lv.approver_key for lv in levels if lv.approver_type == "user")
        )
        return ApprovalPolicyDTO(
            safe_id=safe.id,
            **{f: getattr(safe, f) for f in POLICY_FIELDS},
            levels=tuple(
                ApprovalLevelDTO(
                    position=lv.position,
                    required_approvals=lv.required_approvals,
                    approver_type=lv.approver_type,
                    approver_key=lv.approver_key,
                    approver_name=names.get(lv.approver_key or ""),
                )
                for lv in levels
            ),
        )

    async def save(
        self, safe_id: uuid.UUID, values: dict[str, Any], levels: list[ApprovalLevelDTO]
    ) -> None:
        """Replace the policy and its levels (the caller audits before and after)."""
        safe = await self._session.get(Safe, safe_id)
        for key in POLICY_FIELDS:
            setattr(safe, key, values[key])
        await self._session.execute(
            delete(SafeApprovalLevel).where(SafeApprovalLevel.safe_id == safe_id)
        )
        for lv in levels:
            self._session.add(
                SafeApprovalLevel(
                    safe_id=safe_id,
                    position=lv.position,
                    required_approvals=lv.required_approvals,
                    approver_type=lv.approver_type,
                    approver_key=lv.approver_key,
                )
            )
        await self._session.flush()

    async def approve_holders(self, safe_id: uuid.UUID) -> set[uuid.UUID]:
        """Active users holding 'approve' on the safe through a user, role or (cached)
        directory-group membership."""
        approve = SafeMember.permissions.any(SafePermission.APPROVE.value)
        members = (
            await self._session.execute(
                select(SafeMember.principal_type, SafeMember.principal_key).where(
                    SafeMember.safe_id == safe_id, approve
                )
            )
        ).all()
        user_keys = [k for t, k in members if t == PrincipalType.USER]
        roles = [k for t, k in members if t == PrincipalType.ROLE]
        groups = [k for t, k in members if t == PrincipalType.GROUP]
        found: set[uuid.UUID] = set()
        if user_keys:
            found |= set(
                await self._session.scalars(
                    select(User.id).where(cast(User.id, String).in_(user_keys), User.is_active)
                )
            )
        if roles:
            found |= set(
                await self._session.scalars(
                    select(User.id).where(User.role.in_(roles), User.is_active)
                )
            )
        if groups:
            found |= await self.group_user_ids(groups)
        return found

    async def group_user_ids(self, group_dns: list[str]) -> set[uuid.UUID]:
        """Active users whose cached directory groups include any of these DNs."""
        return set(
            await self._session.scalars(
                select(User.id)
                .join(UserGroupCache, UserGroupCache.user_id == User.id)
                .where(UserGroupCache.groups.overlap(group_dns), User.is_active)
            )
        )
