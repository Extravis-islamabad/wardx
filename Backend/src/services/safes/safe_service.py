"""Safes and their members.

Rules:
- ``safes.manage`` holders create and edit safes and manage members of any safe;
  it grants no access to the accounts inside (that needs membership).
- Others see only safes where they hold ``list``; holders of ``manage_members``
  on a safe manage that safe's members.
- No self-grant: nobody adds or changes a membership whose principal is
  themselves, a group they belong to, or their own role. Refused with
  ``self_grant_forbidden`` and audited as a failure; another admin must do it.
  When the actor's directory groups cannot be verified, group memberships are
  refused the same way (the group might be theirs).
- Every safe and membership change is audited with before and after values.
"""

from __future__ import annotations

import uuid

from src.contracts.dto.safes.safe_dto import SafeDTO, SafeFilterDTO, SafeMemberDTO
from src.core.context import Actor
from src.core.enums import PrincipalType, Role, SafePermission
from src.core.permissions import SAFES_MANAGE
from src.directory.ldap_client import normalise_dn
from src.errors.exceptions import (
    AppError,
    ForbiddenError,
    NotFoundError,
    SelfGrantForbidden,
)
from src.repositories.identity.user_repository import UserRepository
from src.repositories.safes.safe_member_repository import SafeMemberRepository
from src.repositories.safes.safe_repository import SafeRepository
from src.services.audit.audit_service import AuditService
from src.services.safes.safe_access_service import SafeAccessService


class InvalidPrincipal(AppError):
    status_code = 422
    code = "validation_error"


def _safe_view(s: SafeDTO) -> dict:
    return {"name": s.name, "description": s.description, "is_active": s.is_active}


class SafeService:
    def __init__(
        self,
        safes: SafeRepository,
        members: SafeMemberRepository,
        users: UserRepository,
        access: SafeAccessService,
        audit: AuditService,
    ) -> None:
        self._safes = safes
        self._members = members
        self._users = users
        self._access = access
        self._audit = audit

    # ── Safes ──

    async def list(
        self, actor: Actor, *, search: str | None, page: int, page_size: int
    ) -> tuple[list[SafeDTO], int]:
        ids = None if actor.can(SAFES_MANAGE) else await self._access.listable_safe_ids(actor)
        return await self._safes.list(
            SafeFilterDTO(search=search, ids=ids), page=page, page_size=page_size
        )

    async def my_permissions(self, actor: Actor) -> dict[uuid.UUID, frozenset[str]]:
        return await self._access.permissions_by_safe(actor)

    async def get(self, actor: Actor, safe_id: uuid.UUID) -> SafeDTO:
        safe = await self._safes.get(safe_id)
        if safe is None or not (
            actor.can(SAFES_MANAGE)
            or SafePermission.LIST in await self._access.permissions(actor, safe_id)
        ):
            raise NotFoundError("Safe not found")
        return safe

    async def create(self, actor: Actor, values: dict) -> SafeDTO:
        safe_id = await self._safes.create({**values, "created_by": actor.id})
        safe = await self._safes.get(safe_id)
        await self._audit.record(
            actor,
            "safe.create",
            object_type="safe",
            object_id=safe_id,
            details={"after": _safe_view(safe)},
        )
        await self._safes.commit()
        return safe

    async def update(self, actor: Actor, safe_id: uuid.UUID, changes: dict) -> SafeDTO:
        before = await self._safes.get(safe_id, lock=True)
        if before is None:
            raise NotFoundError("Safe not found")
        await self._safes.update(safe_id, changes)
        after = await self._safes.get(safe_id)
        await self._audit.record(
            actor,
            "safe.update",
            object_type="safe",
            object_id=safe_id,
            details={"before": _safe_view(before), "after": _safe_view(after)},
        )
        await self._safes.commit()
        return after

    # ── Members ──

    async def _authorise_members(self, actor: Actor, safe_id: uuid.UUID) -> SafeDTO:
        """Who may see and change a safe's members: safes.manage, or manage_members on it."""
        safe = await self._safes.get(safe_id)
        if safe is None:
            raise NotFoundError("Safe not found")
        if actor.can(SAFES_MANAGE):
            return safe
        perms = await self._access.permissions(actor, safe_id)
        if SafePermission.LIST not in perms:
            raise NotFoundError("Safe not found")
        if SafePermission.MANAGE_MEMBERS not in perms:
            raise ForbiddenError("You need 'manage_members' on this safe or safes.manage")
        return safe

    async def list_members(self, actor: Actor, safe_id: uuid.UUID) -> list[SafeMemberDTO]:
        await self._authorise_members(actor, safe_id)
        return await self._members.list_for_safe(safe_id)

    async def _principal_key(self, principal_type: PrincipalType, key: str) -> str:
        key = key.strip()
        if principal_type == PrincipalType.USER:
            try:
                user_id = uuid.UUID(key)
            except ValueError as exc:
                raise InvalidPrincipal("A user member is named by the user's id") from exc
            if await self._users.get(user_id) is None:
                raise NotFoundError("User not found")
            return str(user_id)
        if principal_type == PrincipalType.GROUP:
            if "=" not in key:
                raise InvalidPrincipal("A group member is named by its distinguished name (DN)")
            return normalise_dn(key)
        try:
            return Role(key.lower()).value
        except ValueError as exc:
            raise InvalidPrincipal(f"Unknown role '{key}'") from exc

    async def _refuse_self_grant(
        self, actor: Actor, action: str, safe_id: uuid.UUID, principal_type: str, key: str
    ) -> None:
        principals = await self._access.principals(actor)
        reason = None
        if principal_type == PrincipalType.USER and key == str(actor.id):
            reason = "yourself"
        elif principal_type == PrincipalType.ROLE and key == str(actor.role):
            reason = "your own role"
        elif principal_type == PrincipalType.GROUP:
            if key in principals.groups:
                reason = "a group you belong to"
            elif not principals.groups_verified:
                reason = "a group (your directory groups cannot be verified right now)"
        if reason is None:
            return
        await self._audit.record(
            actor,
            action,
            object_type="safe",
            object_id=safe_id,
            outcome="failure",
            details={
                "reason": "self_grant_forbidden",
                "principal_type": principal_type,
                "principal_key": key,
            },
        )
        await self._members.commit()
        raise SelfGrantForbidden(
            f"You cannot grant safe permissions to {reason}; another administrator must do it"
        )

    async def add_member(
        self,
        actor: Actor,
        safe_id: uuid.UUID,
        *,
        principal_type: PrincipalType,
        principal_key: str,
        permissions: list[SafePermission],
    ) -> SafeMemberDTO:
        await self._authorise_members(actor, safe_id)
        key = await self._principal_key(principal_type, principal_key)
        await self._refuse_self_grant(actor, "safe_member.add", safe_id, principal_type, key)
        member_id = await self._members.create(
            {
                "safe_id": safe_id,
                "principal_type": principal_type.value,
                "principal_key": key,
                "permissions": sorted({p.value for p in permissions}),
                "created_by": actor.id,
            }
        )
        member = await self._members.get(member_id)
        await self._audit.record(
            actor,
            "safe_member.add",
            object_type="safe",
            object_id=safe_id,
            details={"member_id": str(member_id), "before": None, "after": member.audit_view()},
        )
        await self._members.commit()
        return member

    async def _member(self, safe_id: uuid.UUID, member_id: uuid.UUID) -> SafeMemberDTO:
        member = await self._members.get(member_id, lock=True)
        if member is None or member.safe_id != safe_id:
            raise NotFoundError("Member not found")
        return member

    async def update_member(
        self,
        actor: Actor,
        safe_id: uuid.UUID,
        member_id: uuid.UUID,
        *,
        permissions: list[SafePermission],
    ) -> SafeMemberDTO:
        await self._authorise_members(actor, safe_id)
        before = await self._member(safe_id, member_id)
        await self._refuse_self_grant(
            actor, "safe_member.update", safe_id, before.principal_type, before.principal_key
        )
        await self._members.update(
            member_id, {"permissions": sorted({p.value for p in permissions})}
        )
        after = await self._members.get(member_id)
        await self._audit.record(
            actor,
            "safe_member.update",
            object_type="safe",
            object_id=safe_id,
            details={
                "member_id": str(member_id),
                "before": before.audit_view(),
                "after": after.audit_view(),
            },
        )
        await self._members.commit()
        return after

    async def remove_member(self, actor: Actor, safe_id: uuid.UUID, member_id: uuid.UUID) -> None:
        """Removing narrows access, so it is allowed for your own memberships too."""
        await self._authorise_members(actor, safe_id)
        before = await self._member(safe_id, member_id)
        await self._members.delete(member_id)
        await self._audit.record(
            actor,
            "safe_member.remove",
            object_type="safe",
            object_id=safe_id,
            details={"member_id": str(member_id), "before": before.audit_view(), "after": None},
        )
        await self._members.commit()
