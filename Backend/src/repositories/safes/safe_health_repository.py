"""Membership summaries per active safe, for the health check and the outage warning."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from src.contracts.dto.safes.safe_health_dto import SafeMembershipSummaryDTO
from src.core.enums import PrincipalType
from src.models import Safe, SafeMember, User
from src.repositories.base import BaseRepository


class SafeHealthRepository(BaseRepository):
    async def summaries(self) -> list[SafeMembershipSummaryDTO]:
        users = (
            await self._session.execute(
                select(User.id, User.role, User.auth_source).where(User.is_active)
            )
        ).all()
        active_ids = {str(u.id) for u in users}
        local_ids = {str(u.id) for u in users if u.auth_source == "local"}
        roles = {u.role for u in users}
        local_roles = {u.role for u in users if u.auth_source == "local"}

        safes = (
            await self._session.execute(
                select(Safe.id, Safe.name).where(Safe.is_active).order_by(func.lower(Safe.name))
            )
        ).all()
        counts: dict[uuid.UUID, dict[str, int]] = {
            s.id: dict.fromkeys(("user", "role", "group", "local_user", "local_role"), 0)
            for s in safes
        }
        members = await self._session.execute(
            select(SafeMember.safe_id, SafeMember.principal_type, SafeMember.principal_key).where(
                SafeMember.safe_id.in_(list(counts)), func.cardinality(SafeMember.permissions) > 0
            )
        )
        for safe_id, ptype, key in members.all():
            c = counts[safe_id]
            if ptype == PrincipalType.USER:
                c["user"] += key in active_ids
                c["local_user"] += key in local_ids
            elif ptype == PrincipalType.ROLE:
                c["role"] += key in roles
                c["local_role"] += key in local_roles
            else:
                c["group"] += 1
        return [
            SafeMembershipSummaryDTO(
                safe_id=s.id,
                name=s.name,
                user_members=counts[s.id]["user"],
                role_members=counts[s.id]["role"],
                group_members=counts[s.id]["group"],
                local_user_members=counts[s.id]["local_user"],
                local_role_members=counts[s.id]["local_role"],
            )
            for s in safes
        ]
