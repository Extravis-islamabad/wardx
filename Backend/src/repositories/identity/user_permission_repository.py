"""Direct user grants (iam.user_permissions). Revoking stamps the row; rows are kept."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, select, update

from src.contracts.dto.identity.user_grant_dto import BreakGlassHolderDTO, UserGrantDTO
from src.models import User, UserMfa, UserPermission
from src.repositories.base import BaseRepository

_ACTIVE = UserPermission.revoked_at.is_(None)


def _to_dto(row: UserPermission) -> UserGrantDTO:
    return UserGrantDTO(
        id=row.id,
        user_id=row.user_id,
        codename=row.codename,
        granted_by=row.granted_by,
        granted_at=row.granted_at,
    )


class UserPermissionRepository(BaseRepository):
    async def codenames(self, user_id: uuid.UUID) -> frozenset[str]:
        rows = await self._session.scalars(
            select(UserPermission.codename).where(UserPermission.user_id == user_id, _ACTIVE)
        )
        return frozenset(rows)

    async def codenames_for(self, user_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        if not user_ids:
            return {}
        rows = await self._session.execute(
            select(UserPermission.user_id, UserPermission.codename).where(
                UserPermission.user_id.in_(user_ids), _ACTIVE
            )
        )
        out: dict[uuid.UUID, list[str]] = {}
        for user_id, codename in rows.all():
            out.setdefault(user_id, []).append(codename)
        return out

    async def active(self, user_id: uuid.UUID, codename: str) -> UserGrantDTO | None:
        row = (
            await self._session.execute(
                select(UserPermission).where(
                    UserPermission.user_id == user_id, UserPermission.codename == codename, _ACTIVE
                )
            )
        ).scalar_one_or_none()
        return _to_dto(row) if row else None

    async def grant(self, user_id: uuid.UUID, codename: str, by: uuid.UUID | None) -> UserGrantDTO:
        row = UserPermission(user_id=user_id, codename=codename, granted_by=by)
        self._session.add(row)
        await self._session.flush()
        return _to_dto(row)

    async def revoke(
        self,
        user_id: uuid.UUID,
        codename: str,
        *,
        by: uuid.UUID | None,
        at: datetime,
        reason: str | None = None,
    ) -> bool:
        result = await self._session.execute(
            update(UserPermission)
            .where(UserPermission.user_id == user_id, UserPermission.codename == codename, _ACTIVE)
            .values(revoked_by=by, revoked_at=at, revoke_reason=reason)
        )
        return result.rowcount > 0

    async def holders(self, codename: str) -> list[BreakGlassHolderDTO]:
        """Everyone holding the codename now, with what decides their eligibility."""
        rows = await self._session.execute(
            select(User.id, User.username, User.auth_source, User.is_active, UserMfa.enabled)
            .join(UserPermission, and_(UserPermission.user_id == User.id, _ACTIVE))
            .outerjoin(UserMfa, UserMfa.user_id == User.id)
            .where(UserPermission.codename == codename)
            .order_by(User.username)
        )
        return [
            BreakGlassHolderDTO(
                user_id=uid,
                username=name,
                auth_source=source,
                is_active=active,
                mfa_enabled=bool(mfa),
            )
            for uid, name, source, active, mfa in rows.all()
        ]
