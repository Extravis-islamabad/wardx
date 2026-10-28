"""Effective safe permissions: who may list, use, retrieve or manage what.

A user's permissions on a safe are the union over their direct membership, their
role's membership and the membership of every directory group they belong to.
Directory groups come from the group cache (GroupMembershipService); when they
cannot be verified they count as none (fail closed).

An inactive safe keeps only its administrative permissions (list, view_audit,
manage_members): nobody uses, retrieves or edits accounts in it until it is
reactivated.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from src.contracts.dto.safes.safe_dto import PrincipalsDTO
from src.core.context import Actor
from src.core.enums import SafePermission
from src.errors.exceptions import ForbiddenError, NotFoundError
from src.repositories.safes.safe_member_repository import SafeMemberRepository
from src.repositories.safes.safe_repository import SafeRepository

_INACTIVE_KEEPS = frozenset(
    {SafePermission.LIST, SafePermission.VIEW_AUDIT, SafePermission.MANAGE_MEMBERS}
)


class GroupResolver(Protocol):
    async def groups_for(self, user_id: uuid.UUID) -> tuple[frozenset[str], bool]:
        """(normalised group DNs, verified). Unverified groups must be empty."""


class SafeAccessService:
    def __init__(
        self,
        members: SafeMemberRepository,
        safes: SafeRepository,
        groups: GroupResolver | None = None,
    ) -> None:
        self._members = members
        self._safes = safes
        self._groups = groups
        self._principals: dict[uuid.UUID | None, PrincipalsDTO] = {}

    async def principals(self, actor: Actor) -> PrincipalsDTO:
        """Who the actor is for membership purposes (resolved once per service instance)."""
        if actor.id not in self._principals:
            groups, verified = frozenset(), True
            if self._groups is not None and actor.id is not None:
                groups, verified = await self._groups.groups_for(actor.id)
            self._principals[actor.id] = PrincipalsDTO(
                user_id=actor.id, role=str(actor.role), groups=groups, groups_verified=verified
            )
        return self._principals[actor.id]

    async def permissions_by_safe(self, actor: Actor) -> dict[uuid.UUID, frozenset[str]]:
        found = await self._members.permissions_for(await self.principals(actor))
        active = await self._safes.active_ids()
        return {
            safe_id: frozenset(perms if safe_id in active else perms & _INACTIVE_KEEPS)
            for safe_id, perms in found.items()
        }

    async def permissions(self, actor: Actor, safe_id: uuid.UUID) -> frozenset[str]:
        return (await self.permissions_by_safe(actor)).get(safe_id, frozenset())

    async def listable_safe_ids(self, actor: Actor) -> frozenset[uuid.UUID]:
        return frozenset(
            sid
            for sid, perms in (await self.permissions_by_safe(actor)).items()
            if SafePermission.LIST in perms
        )

    async def require(
        self,
        actor: Actor,
        safe_id: uuid.UUID,
        *any_of: SafePermission,
        what: str = "Account",
    ) -> frozenset[str]:
        """The actor's permissions on the safe, or an error.

        Without ``list`` the object does not exist for the actor (404); with ``list``
        but none of ``any_of`` the action is refused (403).
        """
        perms = await self.permissions(actor, safe_id)
        if SafePermission.LIST not in perms:
            raise NotFoundError(f"{what} not found")
        if any_of and not any(p in perms for p in any_of):
            needed = " or ".join(f"'{p}'" for p in any_of)
            raise ForbiddenError(f"You need the {needed} permission on this safe")
        return perms
