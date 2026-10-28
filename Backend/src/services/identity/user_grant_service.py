"""Direct per-user grants of global codenames: break-glass (``access.emergency``).

Rules:
- Only ``access.emergency`` is grantable, and only to a user who is local
  (never a directory user), active and enrolled in MFA, so break-glass never
  depends on the directory. Groups and roles never hold it.
- Nobody grants to themselves (403 ``self_grant_forbidden``, audited as a failure),
  including re-granting after an automatic revoke: another administrator must.
- Grant and revoke are each audited and each raise a high-severity alert. An admin
  MFA reset revokes the grant automatically (MfaService), audited and alerted too.
"""

from __future__ import annotations

import uuid

from src.contracts.dto.identity.user_grant_dto import BreakGlassHolderDTO
from src.core.context import Actor
from src.core.permissions import ACCESS_EMERGENCY, DIRECT_GRANT_ONLY
from src.errors.exceptions import AppError, ConflictError, NotFoundError, SelfGrantForbidden
from src.models import utcnow
from src.repositories.identity.mfa_repository import MfaRepository
from src.repositories.identity.user_permission_repository import UserPermissionRepository
from src.repositories.identity.user_repository import UserRepository
from src.services.audit.audit_service import AuditService
from src.services.security.alert_service import AlertService


class NotEligible(AppError):
    status_code = 409
    code = "not_eligible"


class UserGrantService:
    def __init__(
        self,
        grants: UserPermissionRepository,
        users: UserRepository,
        mfa: MfaRepository,
        alerts: AlertService,
        audit: AuditService,
    ) -> None:
        self._grants = grants
        self._users = users
        self._mfa = mfa
        self._alerts = alerts
        self._audit = audit

    async def codenames(self, user_id: uuid.UUID | None) -> frozenset[str]:
        return await self._grants.codenames(user_id) if user_id else frozenset()

    async def codenames_for(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        return await self._grants.codenames_for(user_ids)

    async def mfa_enabled_for(self, user_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        return await self._mfa.enabled_for(user_ids)

    async def holders(self, codename: str = ACCESS_EMERGENCY) -> list[BreakGlassHolderDTO]:
        return await self._grants.holders(codename)

    async def _refuse(self, actor: Actor, user_id: uuid.UUID, codename: str, reason: str, exc):
        await self._audit.record(
            actor,
            "user.grant",
            object_type="user",
            object_id=user_id,
            outcome="failure",
            details={"codename": codename, "reason": reason},
        )
        await self._grants.commit()
        raise exc

    async def grant(self, actor: Actor, user_id: uuid.UUID, codename: str) -> None:
        if codename not in DIRECT_GRANT_ONLY:
            raise NotFoundError(f"'{codename}' is not a grantable permission")
        if user_id == actor.id:
            await self._refuse(
                actor,
                user_id,
                codename,
                "self_grant_forbidden",
                SelfGrantForbidden("You cannot grant yourself break-glass access"),
            )
        user = await self._users.get(user_id)
        if user is None:
            raise NotFoundError("User not found")
        mfa = await self._mfa.get(user_id)
        problem = None
        if user.auth_source != "local":
            problem = "directory users cannot hold break-glass access (it must work without it)"
        elif not user.is_active:
            problem = "the user is disabled"
        elif not (mfa and mfa.enabled):
            problem = "the user must be enrolled in MFA first"
        if problem:
            await self._refuse(
                actor, user_id, codename, "not_eligible", NotEligible(f"Not eligible: {problem}")
            )
        if await self._grants.active(user_id, codename) is not None:
            raise ConflictError("The user already holds this permission")
        await self._grants.grant(user_id, codename, actor.id)
        await self._audit.record(
            actor,
            "user.grant",
            object_type="user",
            object_id=user_id,
            details={"codename": codename, "username": user.username},
        )
        await self._alerts.raise_alert(
            actor,
            kind="break_glass.granted",
            message=f"{actor.username} granted break-glass access to {user.username}",
            object_type="user",
            object_id=user_id,
            details={"codename": codename},
        )
        await self._grants.commit()

    async def revoke(self, actor: Actor, user_id: uuid.UUID, codename: str) -> None:
        user = await self._users.get(user_id)
        if user is None:
            raise NotFoundError("User not found")
        if not await self._revoke(actor, user_id, user.username, codename, reason="revoked"):
            raise NotFoundError("The user does not hold this permission")
        await self._grants.commit()

    async def revoke_after_mfa_reset(self, actor: Actor, user_id: uuid.UUID, username: str):
        """Called inside MfaService.admin_reset's transaction (it commits)."""
        for codename in DIRECT_GRANT_ONLY:
            await self._revoke(actor, user_id, username, codename, reason="mfa_reset")

    async def _revoke(
        self, actor: Actor, user_id: uuid.UUID, username: str, codename: str, *, reason: str
    ) -> bool:
        done = await self._grants.revoke(user_id, codename, by=actor.id, at=utcnow(), reason=reason)
        if not done:
            return False
        await self._audit.record(
            actor,
            "user.revoke",
            object_type="user",
            object_id=user_id,
            details={"codename": codename, "username": username, "reason": reason},
        )
        why = " (automatic: MFA was reset)" if reason == "mfa_reset" else ""
        await self._alerts.raise_alert(
            actor,
            kind="break_glass.revoked",
            message=f"{actor.username} revoked break-glass access from {username}{why}",
            object_type="user",
            object_id=user_id,
            details={"codename": codename, "reason": reason},
        )
        return True
